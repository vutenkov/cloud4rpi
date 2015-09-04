#!/bin/sh

### BEGIN INIT INFO
# Provides:          cloud4rpi_service
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Cloud4RPi demon
# Description:       Cloud4RPi demon working with
#                    Raspberry Pi GPIO from Python
### END INIT INFO

# Daemon name, where is the actual executable
CURRUSER=pi
DAEMON=/home/$CURRUSER/cloud4rpi/cloud4rpid.py
DAEMON_NAME=cloud4rpid

# Process name ( For display )
NAME=cloud4rpi-daemon

# Add any command line options for your daemon here
DAEMON_OPTS=""

# This next line determines what user the script runs as.
# Root generally not recommended but necessary if you are using the Raspberry Pi GPIO from Python.
DAEMON_USER=root

# The process ID of the script when it runs is stored here:
PIDFILE=/var/run/$DAEMON_NAME.pid

# Using the lsb functions to perform the operations.
. /lib/lsb/init-functions

do_start () {
    log_daemon_msg "Starting the process $NAME"
    start-stop-daemon --start --background --pidfile $PIDFILE --make-pidfile --user $DAEMON_USER --chuid $DAEMON_USER --startas $DAEMON -- $DAEMON_OPTS
    log_end_msg $?
}
do_stop () {
    log_daemon_msg "Stopping the $NAME process"
    start-stop-daemon --stop --pidfile $PIDFILE --retry 10
    log_end_msg $?
}

# If the daemon is not there, then exit.
test -x $DAEMON || exit 5

case "$1" in

    start|stop)
        do_${1}
        ;;

    restart|reload|force-reload)
        do_stop
        do_start
        ;;

    status)
        status_of_proc "$DAEMON_NAME" "$DAEMON" && exit 0 || exit $?
        ;;

    *)
        echo "Usage: /etc/init.d/$DAEMON_NAME {start|stop|restart|status}"
        exit 1
        ;;

esac
exit 0
