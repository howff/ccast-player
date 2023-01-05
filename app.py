# A Flask web application media server which transcodes for Chromecast
#
# Run with:
#  python -m flask run --host 0.0.0.0

from flask import Flask, jsonify, redirect, render_template, request, url_for
import glob
import logging
import os
import sys
from natsort import natsorted
import time
import pychromecast
from functools import partial
from subprocess import Popen, PIPE
from flask import Flask, Response


from flask.helpers import make_response


app = Flask(__name__)
api_version="1"
desired_chromecast_name = 'TV'
port = 5000
movie_dir = '/mnt/cifs/shared/video/movies'
stream_url = f'http://192.168.1.30:{port}/api/v1/stream?file='


# ---------------------------------------------------------------------
# If running inside the docker comtainer then use /antenna
# otherwise use /opt/DSSingest
# or /ingest/<computername>
# XXX change logging to write to files in logs_dir
#if 'FLASK_APP' in os.environ:
logging_fd = logging.FileHandler(filename='ccast-player.log')
logging_stdout = logging.StreamHandler(sys.stdout)
logging_handlers = [logging_fd, logging_stdout]
#logging.basicConfig(level=logging.DEBUG, handlers=logging_handlers,
#    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s')
#logging.info(f'Starting web server {__name__} with API version v{api_version}')
logger = logging.getLogger(__name__)
logger = app.logger
logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------
# Find the Chromecast
chromecasts = None
while not chromecasts:
    logger.debug('Searching for %s...' % desired_chromecast_name)
    chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[desired_chromecast_name])
logger.debug('Chromecasts:')
logger.debug(chromecasts)
# e.g. [Chromecast('unknown', port=8009, cast_info=CastInfo(services={ServiceInfo(type='mdns', data='Chromecast-282646f9f19ee5392e768c729fcb48a4._googlecast._tcp.local.')}, uuid=UUID('282646f9-f19e-e539-2e76-8c729fcb48a4'), model_name='Chromecast', friendly_name='TV', host='192.168.1.23', port=8009, cast_type='cast', manufacturer='Google Inc.'))]

# Select the first (only if you've given an explicit name)
cast = chromecasts[0]

# ---------------------------------------------------------------------
def mimetype_from_filename(filename):
    for ext in ['.mp3', '.ogg', '.flac', '.wav']:
        if ext in filename:
            return 'audio/mp3'
    for ext in ['.mp4', '.mkv', '.mov', '.avi']:
        if ext in filename:
            return 'video/mp4'
    return 'video/mp4' # XXX ???


# ---------------------------------------------------------------------
""" An object to form a Flask response being a dict with "success":True.
Constructed with an arbitrary object that will be converted to JSON.
Use the web() method to get the response.
"""
class OKResponse:
    """ Handy class to return a suitable dict
    """
    def __init__(self, rc):
        self._rc = rc
    def web(self):
        resp = { "success": True }
        if isinstance(self._rc, dict):
            resp.update(self._rc)
        else:
            resp.update({'value': self._rc})
        logger.debug('returning OK with %s' % resp)
        return resp


# ---------------------------------------------------------------------
""" An object to form a Flask response being a dict with "success":False.
Constructed with an error message.
Use the web() method to get the response.
"""
class ErrorResponse:
    """ Handy class to return a suitable dict for reporting an error.
    Use it like this:
    return ErrorResponse('my error message').web()
    to return { "success": False, "error_message": "my error message" }
    """
    def __init__(self, msg):
        logger.error(msg)
        self._msg = msg
    def web(self):
        # Show detailed error if not running inside docker 
        if not 'FLASK_APP' in os.environ:
            if sys.exc_info()[1]:
                logger.error(sys.exc_info()[1]) # error message
                import traceback
                logger.error(traceback.format_exc()) # traceback
                if sys.__stdin__.isatty():
                    raise
        return { "success": False, "error_message": self._msg }


# ---------------------------------------------------------------------
# Home page returns nothing

def urlencode(filename):
    return filename.replace(' ', '+')

@app.route("/")
def home():

    dir = movie_dir
    mp4 = glob.glob(f'{dir}/*/*.mp4')
    mkv = glob.glob(f'{dir}/*/*.mkv')
    files = natsorted(mp4+mkv)

    html = '<html><head><title>CCast-Player</title></head><body>'
    html += '<p>Using Chromecast: %s' % desired_chromecast_name
    html += '<p>'
    html += '<a href="/api/v1/rescan">Rescan'
    html += '<a href="/api/v1/reboot"> | Reboot'
    html += '<a href="/api/v1/shutdown"> | Shutdown'
    html += '<p>'
    for file in files:
        file = file.replace(dir, '')
        html += '<br><a href="/api/v1/play?file=' + urlencode(file) + '">' + file + '\n'
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
@app.route(f"/api/v{api_version}/rescan")
def rescan():
    logger.debug('rescan')
    return Response('False')

# ---------------------------------------------------------------------
@app.route(f"/api/v{api_version}/reboot")
def reboot():
    logger.debug('reboot')
    return Response('False')

# ---------------------------------------------------------------------
@app.route(f"/api/v{api_version}/shutdown")
def shutdown():
    logger.debug('shutdown')
    pychromecast.discovery.stop_discovery(browser)
    return Response('False')

# ---------------------------------------------------------------------
# /stream?file=path/file.mp4
# Stream the file to the Chromecast, transcoded if necessary.

@app.route(f"/api/v{api_version}/stream")
def stream_file(filepath = None):

    req_file = request.args.get('file', '<None>')
    logger.debug('stream_file got %s' % req_file)

    chunk_size = 2048
    # XXX this command only works for video, not audio
    command = ['ffmpeg', '-i', movie_dir+'/'+req_file,
            '-f', 'mp4',
            '-c', 'copy', '-c:a', 'aac', '-ac', '2',
            '-movflags', '+frag_keyframe+separate_moof+omit_tfhd_offset+empty_moov',
            'pipe:1']
    #command = ['cat', movie_dir+'/'+req_file]
    mtype = mimetype_from_filename(req_file)
    logger.debug('RUN %s' % command)

    process = Popen(command, stdout=PIPE, stderr=DEVNULL, stdin=DEVNULL, bufsize=-1)
    read_chunk = partial(os.read, process.stdout.fileno(), chunk_size)
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
    logger.debug('play_file got %s' % req_file)

    # Start worker thread and wait for cast device to be ready
    logger.debug('Waiting for cast device to be ready...')
    cast.wait()

    logger.debug('Getting media controller...')
    mc = cast.media_controller
    logger.debug('Sending URL...')
    local_file = stream_url + req_file
    local_type = mimetype_from_filename(req_file)
    logger.debug('Asking Chromecast to play %s' % local_file)
    mc.play_media(local_file, local_type)
    logger.debug('Waiting until active...')
    mc.block_until_active()

    logger.debug('Playing status:')
    logger.debug(mc.status)
    # e.g. <MediaStatus {'metadata_type': None, 'title': None, 'series_title': None, 'season': None, 'episode': None, 'artist': None, 'album_name': None, 'album_artist': None, 'track': None, 'subtitle_tracks': {}, 'images': [], 'supports_pause': True, 'supports_seek': True, 'supports_stream_volume': True, 'supports_stream_mute': True, 'supports_skip_forward': False, 'supports_skip_backward': False, 'current_time': 0, 'content_id': 'http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', 'content_type': 'video/mp4', 'duration': None, 'stream_type': 'BUFFERED', 'idle_reason': None, 'media_session_id': 1, 'playback_rate': 1, 'player_state': 'IDLE', 'supported_media_commands': 274447, 'volume_level': 1, 'volume_muted': False, 'media_custom_data': {}, 'media_metadata': {}, 'current_subtitle_tracks': [], 'last_updated': datetime.datetime(2023, 1, 4, 14, 55, 51, 60789)}>

    return OKResponse(f'play file {req_file}').web()



# ---------------------------------------------------------------------
# Main program, instead of python -m flask run --host etc
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=port)

