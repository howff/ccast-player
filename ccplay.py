#!/usr/bin/env python3
# Tell the Chromecast to play the specified file:
#   ccplay.py file.mp4
# You must be running a web server that can serve the file:
#   python -m http.server 8888
 
import pychromecast
from uuid import UUID
import shelve
import sys
import zeroconf

shelve_file = 'ccplay.shelf'
desired_chromecast_name = "TV"
local_url = 'http://192.168.1.30:8888/'
local_file = 'Outlaws - Green Grass and High Tides.mp3'

if len(sys.argv)>1:
    local_file = sys.argv[1]

if '.mp3' in local_file:
    local_type = 'audio/mp3'
else:
    local_type = 'video/mp4'

# Turn it into a local URL
if not 'http' in local_file:
    local_file = local_url + local_file

# Find Chromecast
#   should return something like this:
#     cast = pychromecast.Chromecast(pychromecast.CastInfo(services={pychromecast.ServiceInfo(type='mdns', data='Chromecast-282646f9f19ee5392e768c729fcb48a4._googlecast._tcp.local.')}, uuid=UUID('282646f9-f19e-e539-2e76-8c729fcb48a4'), model_name='Chromecast', friendly_name='TV', host='192.168.1.23', port=8009, cast_type='cast', manufacturer='Google Inc.'))
#   Trying to build one by hand results in an error, but try:

cast = None

# Try to load from database
with shelve.open(shelve_file) as db:
    if desired_chromecast_name in db:
        #print('Loading Chromecast %s from database' % desired_chromecast_name)
        cast_info = db[desired_chromecast_name]
        #print('Loaded %s' % str(cast_info))
        #cast = pychromecast.Chromecast(cast_info = cast_info, tries = 99, timeout = 99, retry_wait = 99, zconf = zeroconf.Zeroconf())
        #print('Created %s' % cast)
        # We don't use this because it doesn't save any time,
        # we still have to wait for the chromecast to become ready which seems to
        # take as much time as waiting for it to become visible on the network.

# Try to create manually
if not cast:
    ip_address = '192.168.1.23'
    port = 8009
    cast_info = pychromecast.CastInfo(
            #services = [pychromecast.ServiceInfo(pychromecast.SERVICE_TYPE_HOST, (ip_address, port))],
            services = {pychromecast.ServiceInfo(type='mdns', data='Chromecast-282646f9f19ee5392e768c729fcb48a4._googlecast._tcp.local.')},
            uuid = UUID('282646f9-f19e-e539-2e76-8c729fcb48a4'),
            model_name='Chromecast',
            friendly_name='TV',
            host = '192.168.1.23',
            port = 8009,
            cast_type = 'cast',
            manufacturer = 'Google Inc.'
            )
    #cast = pychromecast.Chromecast(cast_info = cast_info, tries = 99, timeout = 99, retry_wait = 99)
    # We don't use this because it's missing some important bits so it fails

# Discover Chromecast
if not cast:
    chromecasts = None
    while not chromecasts:
        print('Searching for %s...' % desired_chromecast_name)
        chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[desired_chromecast_name])
    print('Chromecasts:')
    print(chromecasts)
    # e.g. [Chromecast('unknown', port=8009, cast_info=CastInfo(services={ServiceInfo(type='mdns', data='Chromecast-282646f9f19ee5392e768c729fcb48a4._googlecast._tcp.local.')}, uuid=UUID('282646f9-f19e-e539-2e76-8c729fcb48a4'), model_name='Chromecast', friendly_name='TV', host='192.168.1.23', port=8009, cast_type='cast', manufacturer='Google Inc.'))]
    # Select the first (only if you've given an explicit name)
    cast = chromecasts[0]

# Save Chromecast in database for faster use next time
if cast:
    with shelve.open(shelve_file) as db:
        db[desired_chromecast_name] = cast.cast_info

# Start worker thread and wait for cast device to be ready
print('Waiting for cast device to be ready...')
cast.wait()

# Debugging
#print('Device:')
#print(cast.device) # doesn't work
print('Info:')
print(cast.cast_info)
print('Status:')
print(cast.status)

print('Getting media controller...')
mc = cast.media_controller

print('Sending URL...')
#mc.play_media('http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', 'video/mp4')
mc.play_media(local_file, local_type)

print('Waiting until active...')
mc.block_until_active()

print('Playing status:')
print(mc.status)
# e.g. <MediaStatus {'metadata_type': None, 'title': None, 'series_title': None, 'season': None, 'episode': None, 'artist': None, 'album_name': None, 'album_artist': None, 'track': None, 'subtitle_tracks': {}, 'images': [], 'supports_pause': True, 'supports_seek': True, 'supports_stream_volume': True, 'supports_stream_mute': True, 'supports_skip_forward': False, 'supports_skip_backward': False, 'current_time': 0, 'content_id': 'http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4', 'content_type': 'video/mp4', 'duration': None, 'stream_type': 'BUFFERED', 'idle_reason': None, 'media_session_id': 1, 'playback_rate': 1, 'player_state': 'IDLE', 'supported_media_commands': 274447, 'volume_level': 1, 'volume_muted': False, 'media_custom_data': {}, 'media_metadata': {}, 'current_subtitle_tracks': [], 'last_updated': datetime.datetime(2023, 1, 4, 14, 55, 51, 60789)}>

# Can use mc.pause() and mc.play() to control the playback

# Can exit and leave the chromecast playing
# Shut down discovery
print('Shut down discovery but leave ccast playing...')
pychromecast.discovery.stop_discovery(browser)


