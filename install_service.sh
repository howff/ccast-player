#!/bin/bash
# Create a systemd service unit file with the correct paths
# to a) find the logconf file, b) find the database file,
# c) find the virtualenv, and install and start the service.
# This script must be run with sudo.

name="ccastplayer"

currentuser=$(logname)
currentdir=$(pwd)
if [ ! -f "$currentdir/$name.logconf" ]; then
	echo "Error: cannot find $name.logconf in $currentdir" >&2
	exit 1
fi
if [ ! -f "$currentdir/$name.service" ]; then
	echo "Error: cannot find $name.service in $currentdir" >&2
	exit 1
fi
if [ ! -d "$currentdir/venv" ]; then
	echo "Error: cannot find virtualenv called 'venv' in $currentdir" >&2
	exit 1
fi


if [ -f /etc/systemd/system/${name}.service ]; then
	echo "Remove old version of ${name}.service"
	sudo systemctl stop ${name}.service
	sudo systemctl disable ${name}.service
	sudo rm -f /etc/systemd/system/${name}.service
	sudo systemctl daemon-reload
	sudo systemctl reset-failed
fi

echo "Modify log config with current path"
sed \
	-e "s,LOGDIR,$currentdir," \
	${name}.logtemplate > ${name}.logconf

echo "Modify service unit file with current path"
sed -i \
	-e "s,ExecStart=.*/gunicorn,ExecStart=${currentdir}/venv/bin/gunicorn," \
	-e "s,--chdir [^ ]*,--chdir ${currentdir}," \
	-e "s,--user [^ ]*,--user ${currentuser}," \
	-e "s,--log-config [^ ]*,--log-config ${currentdir}/${name}.logconf," \
	${name}.service

echo "Copy unit file to /etc"
sudo cp ${name}.service /etc/systemd/system/

echo "Enable the service"
sudo systemctl enable ${name}.service

echo "Start the service"
sudo systemctl start  ${name}.service

echo "To view the service status:"
echo " sudo systemctl -l --no-pager status ${name}.service"

echo "To view the service log:"
echo " sudo journalctl -u ${name}.service"
