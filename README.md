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
virtualenv venv
source venv/bin/activate
cd ccast-player
pip install -r requirements.txt
```

# Configuration

The seek position database is stored in the current directory (edit the script to change this).

# Usage

Start server
```
python -m flask run
OR
./app.py
```

It will take a few seconds to discover the Chromecasts on your network, sometimes up to a minute.
Point your browser at http://localhost:5000/ select a movie to watch it.

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
```

Play a file
```
curl http://localhost:5000/api/v1/play?file=test1.mp3
```
You must URL-encode the filename, i.e. no spaces.

The `play` method will instruct the Chromecast to start playing from a particular URL.
That URL will be the `stream` method which outputs the movie to the Chromecast,
and transcodes in the process.
```
http://localhost:5000/api/v1/stream?file=test1.mp3
```

# Troubleshooting

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
