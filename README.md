# ccast-player

A Media Player for the Chromecast. Implemented in Python. Runs on Linux and maybe MacOS/Windows (not tested).
It allows you to play audio and video files, which are available on your local computer, onto a Google Chromecast.
The intended use case is where you have a collection of videos and want to be able to use a web browser on a different computer in your home network to cast them to your TV.

* Provides a web server which lists all your movies
* Casts a movie file to your Chromecast when you click on a movie title

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

Edit the script to change the path to your movies.

# Usage

Start server
```
python -m flask run --host 0.0.0.0 &
OR
./app.py [--host 0.0.0.0] [--port 5000] [--chromecast "Living Room"] [--media /path/to/files]
```

It will take a few seconds to discover the Chromecasts on your network, sometimes up to a minute.
Point your browser at http://localhost:5000/ select a movie to watch it.

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
and possibly transcodes in the process.
```
http://localhost:5000/api/v1/stream?file=test1.mp3
```

# How it works

* Listen for Chromecasts
* Connect to Chomecast
* Tell Chromecast to play from a URL
* Listen for requests for that URL
* Stream media back to the Chromecast client

# To do

* Currently leaves behind the process doing the streaming
* Remember position so user can restart movie from where they stopped
* Solve both by having a monitor thread which sees what's playing and at what position,
and when same media played again it can send a seek.

# See also

* mkchromecast - should do exactly the same as this code, and more, but I couldn't
get it working, and it's been abandoned by the author. It seems to *require* either
PulseAudio or ALSA so wouldn't work on my headless server.
* catt - no GUI and no way to play local files?
* casttube - similar
* pychromecast - what this server is built on
