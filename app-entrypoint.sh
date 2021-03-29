#!/bin/sh
cd $WORKDIR

echo "Collect static files"
python manage.py collectstatic --noinput

echo "Compress static files"
python manage.py compress --extension=.haml,.html

echo "Compile Messages"
python manage.py compilemessages

echo "Starting server"
gunicorn ureport.wsgi:application --max-requests 5000 -b 0.0.0.0:8080 -c $PROJECT_PATH/gunicorn.conf.py
