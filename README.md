# ccast-player

A Media Player for the Chromecast. Implemented in Python. Runs on Linux and maybe MacOS/Windows (not tested).
It allows you to play audio and video files, which are available on your local computer, onto a Google Chromecast.
The intended use case is where you have a collection of videos and want to be able to use a web browser on a different computer in your home network to cast them to your TV.

* Provides a web server which lists all your movies
* Casts a movie file to your Chromecast when you click on a movie title
* Restarts a movie where you left off, if you stop watching before the end

# Installation

```
sudo apt install ffmpeg # or install ffmpeg some other way
git clone https://github.com/howff/ccast-player
cd ccast-player
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
sudo mkdir /var/log/ccastplayer
sudo ./install_service.sh
```

# Configuration

The seek position database is stored in the current directory.
The log configuration file is stored in the current directory.
When run as a service the ccastplayer.service file will chdir to this
installation directory to find the database and will use the full
path to the log configuration file. To change this either change the
service file and re-install it, or edit the `install_service.sh` script.
The logconf file specifies `/var/log/ccastplayer` as the log directory
on the assumption the service is run by systemd but you can change this.

# Usage

Start server
```
python -m flask run
OR
./app.py
OR
gunicorn --bind 0.0.0.0:5000 --chdir $(pwd) --log-config ccastplayer.logconf --workers=1 app:app
```

It will take a few seconds to discover the Chromecasts on your network, sometimes up to a minute.

Point your browser at http://localhost:5000/ and select a movie to watch it,
which if you've started watching before will resume from the last location.

Additional options are available:

The list of movies can be sorted:
* By name - http://localhost:5000/?sort=name (the default, uses a natural sorting method)
* By most recently modified file - http://localhost:5000/?sort=mtime (base on the modification time of the movie file)
* By most recently accessed file - http://localhost:5000/?sort=atime (based on the access time of the movie file)
* By most recently watched file - http://localhost:5000/?sort=wtime (based on the time when a seek position was recorded in the database)


Full set of options:
```
usage: app.py [-h] [-v] [-d] [--host HOST] [--port PORT]
   [--chromecast CHROMECAST] [--media MEDIA]
   [--media_dump] [--db_dump] [--db_set DBSET]

  -h, --help            show this help message and exit
  -d, --debug           debug
  --host HOST           network interfaces to listen on (default 0.0.0.0)
  --port PORT           network port to listen on (default 5000)
  --chromecast NAME     name of Chromecast to cast to (default TV)
  --media MEDIA         location of media files (default /mnt/cifs/shared/video/movies)
  --media_dump          display the list of files (as HTML) then exit
  --db_dump             display the database then exit
  --db_set DBSET        set seek position (in seconds) filename=seconds (e.g. file.mp4=60)
```

You will want to specify at least:
* --chromecast with the name of your Chromecast (the friendly name not the model name)
* --media with the path to your directory of movie files (it will search all directories inside there too)

# API

List all movies
```
curl http://localhost:5000/
curl http://localhost:5000/?sort=XXX where XXX is name,mtime,atime,wtime
```

Play a file
```
curl http://localhost:5000/api/v1/play?file=test1.mp3
curl http://localhost:5000/api/v1/play?file=test1.mp3?resume=0
curl http://localhost:5000/api/v1/play?file=test1.mp3?subtitles=1
```
You must URL-encode the filename, i.e. no spaces.

The `play` method will instruct the Chromecast to start playing from a particular URL.
That URL will be the `stream` method which outputs the movie to the Chromecast,
and transcodes in the process.
```
http://localhost:5000/api/v1/stream?file=test1.mp3
```

Use `resume=0` to ignore the seek position in the database and start watching from the beginning.

Use `subtitles=1` to display the subtitles from the WEBVTT format file
with the movie filename plus `.vtt` appended (i.e. append .vtt, don't replace .mp4 with .vtt).
You can use ffmpeg to convert srt to vtt format.
The movie file listing will only show a Subtitles option if this file is available.

# Troubleshooting

* Make sure the TV is switched on when starting the service or calling the web page otherwise it will hang (even if all you want to do is to download a file)

* Check the movie file itself, some are 4k and (currently) won't be downsampled to play on a 1080p chromecast/tv.

* Also check the transcoding can run at full speed by looking at the ffmpeg output because if it can't you'll get stuttering.

* Try `avahi-browse _googlecast._tcp` to see if your Chromecast is responding on the network

* Use `--media_dump` to see which files are being found by the search

* Use `--db_dump` to see the content of the database which holds the seek position
of each movie watched.  The database is in sqlite3 format so you can see/edit it using
the `sqlite3` program if installed.

* Use `--db_set` to change the seek position of a movie, for example to change it to
10 minutes (600 seconds) for file1.mp4 use `--db_set file1.mp4=600`

* Try downgrading protobuf package to 3.20.x or lower.
pip install protobuf==3.20.1
or Set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python (but this will use pure-Python parsing and will be much slower).

* Try downgrading zeroconf package to 0.24.3 or something?

# How it works

* Listen for Chromecasts
* Connect to Chomecast
* Tell Chromecast to play from a URL
* Listen for requests for that URL
* Stream media back to the Chromecast client

# See also

* https://github.com/muammar/mkchromecast - should do exactly the same as this code, and more, but I couldn't get it working, and it's been abandoned by the author. It seems to *require* either PulseAudio or ALSA so wouldn't work on my headless server.
* https://github.com/skorokithakis/catt - no GUI and no way to play local files?
* https://github.com/ur1katz/casttube - similar
* https://github.com/yt-dlp/yt-dlp - used by the above
* https://github.com/home-assistant-libs/pychromecast - what this server is built on
* https://github.com/palaviv/caster - includes subtitle support

