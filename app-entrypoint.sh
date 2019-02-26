#!/bin/sh
cd $WORKDIR

echo "Collect static files"
python manage.py collectstatic --noinput

echo "Compress static files"
python manage.py compress --extension=.haml,.html

echo "Compile Messages"
python manage.py compilemessages

echo "Starting server"
gunicorn ureport.wsgi --log-config gunicorn-logging.conf -c gunicorn.conf.py --workers 4
