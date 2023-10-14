#!/usr/bin/env python3
# A Flask web application media server which transcodes for Chromecast
#
# Run with:
#  python -m flask run --host 0.0.0.0
# or just:
#  ./app.py --help
# or with gunicorn:
#  /path/venv/bin/gunicorn --bind 0.0.0.0:5000 --chdir /path/ccast-player --user arb app:app

import argparse
import datetime # used when eval(MediaStatus)
import glob
import json
import logging, logging.handlers
import os
import re
import sys
from natsort import natsorted
from pydal import DAL, Field
import pprint
import signal
import socket
import time
import threading
import urllib.parse
import pychromecast
from functools import partial
from subprocess import Popen, PIPE, DEVNULL
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
#from flask.helpers import make_response


app = Flask(__name__)
api_version="1"
desired_chromecast_name = 'TV'
port = 5000
movie_dir = '/mnt/cifs/shared/video/movies'
stream_url = f'http://192.168.1.30:{port}/api/v1/stream?file='
audio_file_ext = ['.mp3', '.opus', '.ogg', '.flac', '.wav']
video_file_ext = ['avi', 'mov', 'mkv', 'mp4', 'flv', 'ts']
cast = None
global_file_playing = None
global_pid = None
global_process = None
global_duration = -1
global_seekpos = 0


# ---------------------------------------------------------------------
# Configure logging
# Uncomment the basicConfig lines to see output from Flask/pychromecast.

logging_fd = logging.handlers.RotatingFileHandler(filename='ccast-player.log', maxBytes=64*1024*1024, backupCount=9)
logging_stdout = logging.StreamHandler(sys.stdout)
logging_handlers = [logging_fd, logging_stdout]
#logging.basicConfig(level=logging.DEBUG, handlers=logging_handlers,
#    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s')
logger = app.logger


# ---------------------------------------------------------------------
# Get the local host IP address so we can construct a URL to send to Chromecast
# Returns a string such as "192.168.1.30", or "127.0.0.1" if it cannot be found.

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


# ---------------------------------------------------------------------
# Maintain a database of the current seek position (duration) for files
# which have been partially watched.

class SeekDB:
    # Not used yet!
    def __init__(self):
        self.db = DAL('sqlite://ccastplayer.sqlite', folder='.')
        self.db.define_table('SeekPos', Field('file', unique=True), Field('seek'))
    def get_seekpos(self, filename):
        for row in db(db.SeekPos.file == filename).select(db.SeekPos.seek):
            logger.debug('Got seek position %s for %s' % (row, filename))
            return row['seek']
        return None
    def update_seekpos(self, filename, seconds):
        db.SeekPos.update_or_insert(db.SeekPos.file == filename, file = filename, seek = seekpos)
        db.commit()
        logger.debug('Set seek position %s for %s' % (seekpos, filename))
    def dump(self):
        for row in db().select(db.SeekPos.ALL):
            print(row)


def db_init():
    """ Open and configure the database. Call this to get a db handle
    before any reading or writing. Internal use only """

    db = DAL('sqlite://ccastplayer.sqlite', folder='.')
    db.define_table('SeekPos', Field('file', unique=True), Field('seek'))
    return db


def db_get_seekpos(filename):
    """ Return the seek position for the given filename, or None if not found. """

    db = db_init()
    for row in db(db.SeekPos.file == filename).select(db.SeekPos.seek):
        logger.debug('Got seek position %s for %s' % (row, filename))
        return row['seek']
    return None


def db_update_seekpos(filename, seekpos):
    """ Add a record to the database (or update an existing record)
        with a value of seekpos for the given filename. """

    db = db_init()
    db.SeekPos.update_or_insert(db.SeekPos.file == filename, file = filename, seek = seekpos)
    db.commit()
    logger.debug('Set seek position %s for %s' % (seekpos, filename))


def db_dump():
    """ Print all rows in the database """

    db = db_init()
    for row in db().select(db.SeekPos.ALL):
        print(row)


# ---------------------------------------------------------------------
# This function never exits, it periodically queries the Chromecast status
# and updates global variables with the current seek position.

def monitor_chromecast(cast):
    """ Periodically get the status of the Chromecast
    if streaming our file then remember the current seek position (duration)
    otherwise assume streaming stopped so kill the ffmpeg process
    then write the final duration to the database.
    e.g. [2023-01-05 16:40:22,036] DEBUG in app: <MediaStatus {'metadata_type': None, 'title': None, 'series_title': None, 'season': None, 'episode': None, 'artist': None, 'album_name': None, 'album_artist': None, 'track': None, 'subtitle_tracks': [], 'images': [], 'supports_pause': True, 'supports_seek': True, 'supports_stream_volume': True, 'supports_stream_mute': True, 'supports_skip_forward': False, 'supports_skip_backward': False, 'current_time': 5.631622, 'content_id': 'http://192.168.1.30:5000/api/v1/stream?file=/Alpinist/The.Alpinist.2021.1080p.WEB-DL.DD5.1.H.264-TEPES.mkv', 'content_type': 'video/mp4', 'duration': 10.219, 'stream_type': 'BUFFERED', 'idle_reason': None, 'media_session_id': 1, 'playback_rate': 1, 'player_state': 'BUFFERING', 'supported_media_commands': 274447, 'volume_level': 1, 'volume_muted': False, 'media_custom_data': {}, 'media_metadata': {}, 'current_subtitle_tracks': [], 'last_updated': datetime.datetime(2023, 1, 5, 16, 40, 21, 781787)}>
    """

    global global_duration
    global global_file_playing

    logger.debug('Monitor thread running')
    while True:
        if cast.media_controller.status:
            status = str(cast.media_controller.status) # no method to get properties
            status_dict = eval(status[13:-1])          # strip off the class name
            content_id = status_dict.get('content_id', '')
            if not content_id:
                content_id = ''
            duration = status_dict.get('duration', -1)
            if not duration:
                duration = -1
            logger.debug('Media Status: at %f playing %s' % (duration, content_id))
            if global_file_playing:
                if global_file_playing in content_id:
                    #logger.debug('content_id contains filename (%s)' % (global_file_playing))
                    if duration > 0:
                        global_duration = duration + global_seekpos # duration is an offset from the where we started which might have been seeked
                else:
                    #logger.debug('content_id NOT contains filename %s' % (global_file_playing))
                    logger.debug('Killing PID %s' % global_pid)
                    os.kill(global_pid, signal.SIGKILL) # XXX hacky. only KILL works (prob because blocked in I/O) INT and TERM don't kill
                    global_process.wait()
                    logger.debug('Updating database with duration %f for %s' % (global_duration, global_file_playing))
                    db_update_seekpos(global_file_playing, global_duration)
                    global_file_playing = None
            else:
                logger.debug('No global_file_playing')
        time.sleep(2)


# ---------------------------------------------------------------------
# Find the Chromecast

def find_chromecast(desired_chromecast_name):
    """ Find the named Chromecast and return a Cast object """

    chromecasts = None
    while not chromecasts:
        logger.debug('Searching for "%s" ...' % desired_chromecast_name)
        chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[desired_chromecast_name])
    logger.debug('Discovered Chromecasts: %s' % chromecasts)
    # e.g. [Chromecast('unknown', port=8009, cast_info=CastInfo(services={ServiceInfo(type='mdns', data='Chromecast-282646f9f19ee5392e768c729fcb48a4._googlecast._tcp.local.')}, uuid=UUID('282646f9-f19e-e539-2e76-8c729fcb48a4'), model_name='Chromecast', friendly_name='TV', host='192.168.1.23', port=8009, cast_type='cast', manufacturer='Google Inc.'))]

    # Select the first (only if you've given an explicit name)
    cast = chromecasts[0]
    return cast


def start_chromecast_monitor(cast):
    """ Start a background thread to monitor the Chromecast
    and update some global variables with the current seek position """

    monitor_thread = threading.Thread(target = monitor_chromecast, args = (cast,))
    monitor_thread.start()


# ---------------------------------------------------------------------

def mimetype_from_filename(filename):
    """ Return a mimetype suitable for the given filename extension """

    ext_regex = '.*\.(' + '|'.join(audio_file_ext) + ')$'
    if re.match(ext_regex, filename):
        return 'audio/mp3'
    ext_regex = '.*\.(' + '|'.join(video_file_ext) + ')$'
    if re.match(ext_regex, filename):
        return 'video/mp4'
    return 'video/mp4' # XXX default to video ???


# ---------------------------------------------------------------------
# Home page returns list of files available to play

def urlencode(filename):
    #return filename.replace(' ', '+')
    return urllib.parse.quote_plus(filename)

def prettyname(filename):
    return filename.replace('/', ' / ')

@app.route("/")
def home():

    # Collect a list of movie files underneath the media directory
    dir = movie_dir
    files = []
    ext_regex = '.*\.(' + '|'.join(video_file_ext) + ')$'
    for root, dirslist, fileslist in os.walk(dir, followlinks = True):
        files += [os.path.join(root, f) for f in fileslist if re.match(ext_regex, f)]
    files = natsorted(files)

    # Create HTML document listing movie files with option to Restart from beginning
    html = '<html><head><title>CCast-Player</title></head><body>\n'
    html += '<p class="cast">Using Chromecast: %s</p>\n' % desired_chromecast_name
    html += '<p class="menu">'
    html += '<a class="menuitem" href="/api/v1/status">| Status'
    html += '<a class="menuitem" href="/api/v1/rescan">| Rescan'
    html += '<a class="menuitem" href="/api/v1/reboot"> | Reboot'
    html += '<a class="menuitem" href="/api/v1/shutdown"> | Shutdown</p>\n'
    html += '<p>\n'
    for file in files:
        # Strip off the path prefix
        file = file.replace(dir, '')
        html += '<br><a class="file" href="/api/v1/play?file=' + urlencode(file) + '">' + prettyname(file) + '</a>\n'
        html += '  <a class="resume" href="/api/v1/play?file=' + urlencode(file) + '&resume=0">[Restart]</a>\n'
    html += '</body></html>'
    return Response(html)


# ---------------------------------------------------------------------
# Help page returns links demonstrating the API

@app.route(f"/help")
def help_root():
    return redirect(url_for('help'))

@app.route(f"/api/help")
def help_api():
    return redirect(url_for('help'))

@app.route(f"/api/v{api_version}/help")
def help():
    return render_template('help.html',
        api_ver = api_version)


# ---------------------------------------------------------------------
@app.route(f"/api/v{api_version}/status")
def status():
    """ Return Chromecast status """
    if cast.media_controller.status:
        status = str(cast.media_controller.status) # no method to get properties
        status_dict = eval(status[13:-1])          # strip off the class name
        return Response('<pre>' + pprint.pformat(status_dict, indent=4) + '</pre>')
    return Response('Chromecast not found')


# ---------------------------------------------------------------------
@app.route(f"/api/v{api_version}/rescan")
def rescan():
    """ Look for the Chromecast again """

    logger.debug('rescan')
    cast = find_chromecast(desired_chromecast_name)
    start_chromecast_monitor(cast)
    return Response('Please wait a minute for the Chromecast Discovery to complete')


# ---------------------------------------------------------------------
@app.route(f"/api/v{api_version}/reboot")
def reboot():
    logger.debug('reboot')
    return Response('Not yet implemented')


# ---------------------------------------------------------------------
@app.route(f"/api/v{api_version}/shutdown")
def shutdown():
    logger.debug('shutdown')
    pychromecast.discovery.stop_discovery(browser)
    return Response('Not yet implemented')


# ---------------------------------------------------------------------
# /stream?file=path/file.mp4
# Stream the file to the Chromecast, transcoded if necessary.

@app.route(f"/api/v{api_version}/stream")
def stream_file(filepath = None):

    # Need to perform validation on req_file to ensure it's a genuine file under movie_dir
    # and not going to access anything outside movie_dir (e.g. parent directory)
    # and not going to look like an additional argument to ffmpeg.
    req_file = request.args.get('file', '<None>')
    req_resume = request.args.get('resume', None)

    logger.debug('stream_file got file %s resume %s' % (req_file, req_resume))
    global global_file_playing, global_pid, global_process, global_seekpos

    # Get seek position from the database if possible but override with param passed in URL
    # resume=0 starts from the beginning.
    seek_seconds = 0
    seekpos = db_get_seekpos(req_file)
    if req_resume is not None:
        seekpos = float(req_resume)
    if seekpos:
        global_seekpos = float(seekpos) # need to keep global so 'duration' can be added to it
        seek_seconds = global_seekpos

    chunk_size = 2048
    # XXX this command only works for video, not audio
    command = ['ffmpeg',
            '-ss', str(seek_seconds),
            '-i', movie_dir+'/'+req_file,
            '-f', 'mp4',
            '-c', 'copy', '-c:a', 'aac', '-ac', '2',
            '-movflags', '+frag_keyframe+separate_moof+omit_tfhd_offset+empty_moov',
            'pipe:1']
    #command = ['cat', movie_dir+'/'+req_file]
    mtype = mimetype_from_filename(req_file)
    logger.debug('RUN %s' % command)

    global_process = Popen(command, stdout=PIPE, stderr=DEVNULL, stdin=DEVNULL, bufsize=-1)
    global_file_playing = req_file
    global_pid = global_process.pid
    read_chunk = partial(os.read, global_process.stdout.fileno(), chunk_size)
    try:
        return Response(iter(read_chunk, b""), mimetype=mtype)
    except:
        # XXX this never seems to be called
        logger.error('Connection closed?')
        return Response('ABORTED')


# ---------------------------------------------------------------------
# /play?file=path/file.mp4
# Asks the Chromecast to play the file by giving it a URL to ourself.

@app.route(f"/api/v{api_version}/play")
def play_file(filepath = None):

    req_file = request.args.get('file', '<None>')
    req_resume = request.args.get('resume', None)
    logger.debug('play_file got %s resume %s' % (req_file, req_resume))

    # Start worker thread and wait for cast device to be ready
    logger.debug('Waiting for cast device to be ready...')
    cast.wait()

    logger.debug('Getting media controller...')
    mc = cast.media_controller
    logger.debug('Sending URL...')
    local_file = stream_url + req_file
    if req_resume is not None:
        local_file += '&resume=%s' % req_resume
    local_type = mimetype_from_filename(req_file)
    logger.debug('Asking Chromecast to play %s' % local_file)
    mc.play_media(local_file, local_type)
    logger.debug('Waiting until active...')
    mc.block_until_active()

    logger.debug('Playing status:')
    logger.debug(mc.status)
    # e.g. <MediaStatus {'metadata_type': None, 'title': None, 'series_title': None, 'season': None, 'episode': None, 'artist': None, 'album_name': None, 'album_artist': None, 'track': None, 'subtitle_tracks': {}, 'images': [], 'supports_pause': True, 'supports_seek': True, 'supports_stream_volume': True, 'supports_stream_mute': True, 'supports_skip_forward': False, 'supports_skip_backward': False, 'current_time': 0, 'content_id': 'http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', 'content_type': 'video/mp4', 'duration': None, 'stream_type': 'BUFFERED', 'idle_reason': None, 'media_session_id': 1, 'playback_rate': 1, 'player_state': 'IDLE', 'supported_media_commands': 274447, 'volume_level': 1, 'volume_muted': False, 'media_custom_data': {}, 'media_metadata': {}, 'current_subtitle_tracks': [], 'last_updated': datetime.datetime(2023, 1, 4, 14, 55, 51, 60789)}>

    return Response(f'play file {req_file}')



# ---------------------------------------------------------------------
# Main program, instead of python -m flask run --host etc

def main():
    global cast

    parser = argparse.ArgumentParser(description='CCast-Player')
    parser.add_argument('-v', '--verbose', action="store_true", help='verbose (logs to screen when running with --service)')
    parser.add_argument('-d', '--debug', action="store_true", help='debug')
    parser.add_argument('--service', action="store_true", help='run as a daemon service (logs to a file)')
    parser.add_argument('--host', dest='host', action="store", help='network interfaces to listen on (default %(default)s)', default='0.0.0.0')
    parser.add_argument('--port', dest='port', action="store", help='network port to listen on (default %(default)s)', default='5000')
    parser.add_argument('--chromecast', dest='chromecast', action="store", help='name of Chromecast to cast to (default %(default)s)', default='TV')
    parser.add_argument('--media', dest='media', action="store", help='location of media files (default %(default)s)', default='/mnt/cifs/shared/video/movies')
    parser.add_argument('--media_dump', dest='mediadump', action="store_true", help="display the list of files")
    parser.add_argument('--db_dump', dest='dbdump', action="store_true", help="display the database")
    parser.add_argument('--db_set', dest='dbset', action="store", help="set seek position (in seconds) filename=seconds (e.g. file.mp4=60)")
    args = parser.parse_args()

    if args.service:
        log_handlers = [logging_fd]
        if args.verbose:
            handlers += logging_stdout
        logging.basicConfig(handlers=log_handlers,
            format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s')

    if args.debug:
        logger.setLevel(logging.DEBUG)

    if args.dbset:
        equ = args.dbset.rindex('=')
        filename = args.dbset[:equ]
        seconds  = args.dbset[equ+1:]
        db_update_seekpos(filename, seconds)

    if args.dbdump:
        db_dump()
        sys.exit(0)

    if args.mediadump:
        print(str(home().data).replace('\\n','\n'))
        sys.exit(0)

    desired_chromecast_name = args.chromecast
    port = int(args.port)
    movie_dir = args.media
    ip = get_local_ip()
    stream_url = f'http://{ip}:{port}/api/v1/stream?file=' # XXX why not just use a relative URL?

    #logger.debug('app.root_path = %s' % app.root_path)
    #logger.debug('app.instance_path = %s' % app.instance_path)
    logger.debug('chromecast = %s' % desired_chromecast_name)
    logger.debug('ip = %s' % ip)
    logger.debug('port = %s' % port)
    logger.debug('movie_dir = %s' % movie_dir)

    logger.info('Searching for Chromecast "%s"' % desired_chromecast_name)
    cast = find_chromecast(desired_chromecast_name)
    start_chromecast_monitor(cast)

    logger.info('Starting web server')
    app.run(host=args.host, port=args.port)


# Gunicorn entry point generator -- calls main() with command line arguments
# generated from gunicorn app(foo=bar)
def appNOTUSED(*args, **kwargs):
    # Gunicorn CLI args are useless.
    # https://stackoverflow.com/questions/8495367/
    #
    # Start the application in modified environment.
    # https://stackoverflow.com/questions/18668947/
    #
    sys.argv = ['--gunicorn']
    for k in kwargs:
        sys.argv.append("--" + k)
        sys.argv.append(kwargs[k])
    return main()


if __name__ == "__main__":
    main()
