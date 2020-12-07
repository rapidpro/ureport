#!/bin/bash
set -e

case $1 in
    supervisor)
        /usr/bin/supervisord -n -c supervisor-app.conf
    ;;
esac

exec "$@"
