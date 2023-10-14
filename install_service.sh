#!/bin/bash

name="ccastplayer.service"

echo "Remove old version of $name"
sudo systemctl stop $name
sudo systemctl disable $name
sudo rm -f /etc/systemd/system/$name
sudo systemctl daemon-reload
sudo systemctl reset-failed

echo "Copy unit file to /etc"
sudo cp $name /etc/systemd/system/

echo "Enable the service"
sudo systemctl enable $name

echo "Start the service"
sudo systemctl start  $name

echo "Service status:"
echo " sudo systemctl -l --no-pager status $name"

echo "Service log:"
echo " sudo journalctl -u $name"
