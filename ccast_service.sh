#!/bin/bash
cd ~arb/src/cast/ccast-player/
source ../venv/bin/activate
nohup ./app.py --service --debug &
