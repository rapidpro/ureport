#!/bin/bash

set -e

APP_CELERY_INIT="ureport"

bootstrap_conf(){
	find "${PROJECT_PATH}" -not -user "${APP_UID}" -exec chown "${APP_UID}:${APP_GID}" {} \+
}

bootstrap_conf

if [[ "start" == "$1" ]]; then
	echo "Collect static files"
	python manage.py collectstatic --noinput || echo "Deu erro em: collectstatic"

	echo "Compress static files"
	python manage.py compress --extension=.haml,.html

	echo "Compile Messages"
	python manage.py compilemessages

	# gunicorn ureport.wsgi:application --max-requests 5000 -b 0.0.0.0:8080 -c $PROJECT_PATH/gunicorn.conf.py
	exec gosu "${APP_UID}:${APP_GID}" gunicorn ureport.wsgi:application --max-requests 5000 --bind "0.0.0.0:${APP_PORT}" --capture-output --error-logfile - -c $PROJECT_PATH/gunicorn.conf.py
elif [[ "celery-worker" == "$1" ]]; then
	exec gosu "${APP_UID}:${APP_GID}" celery -A "${APP_CELERY_INIT}" worker --loglevel=INFO -E
elif [[ "celery-beat" == "$1" ]]; then
	exec gosu "${APP_UID}:${APP_GID}" celery -A "${APP_CELERY_INIT}" beat --loglevel=INFO
elif [[ "healthcheck-celery-worker" == "$1" ]]; then
	HEALTHCHECK_OUT=$( gosu "${APP_UID}:${APP_GID}" celery -A "${APP_CELERY_INIT}" inspect ping -d "celery@${HOSTNAME}"  2>&1 )
	echo "${HEALTHCHECK_OUT}"
	fgrep -qs "celery@${HOSTNAME}: OK" <<<"${HEALTHCHECK_OUT}" || exit 1
	exit 0
elif [[ "healthcheck-http-get" == "$1" ]]; then
	gosu "${APP_UID}:${APP_GID}" curl -SsLf "${2}" -o /tmp/null --connect-timeout 3 --max-time 20 -w "%{http_code} %{http_version} %{response_code} %{time_total}\n" || exit 1
	exit 0
elif [[ "healthcheck" == "$1" ]]; then
	gosu "${APP_UID}:${APP_GID}" curl -SsLf "http://127.0.0.1:${APP_PORT}/" -o /tmp/null --connect-timeout 3 --max-time 20 -w "%{http_code} %{http_version} %{response_code} %{time_total}\n" || exit 1
	exit 0
fi

exec "$@"
