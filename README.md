# U-Report 

[![Build Status](https://github.com/rapidpro/ureport/workflows/CI/badge.svg)](https://github.com/rapidpro/ureport/actions?query=workflow%3ACI) 

This is the U-Report dashboard built on data collected by RapidPro.

Built for UNICEF by Nyaruka - http://nyaruka.com

Getting Started
================

Install dependencies
```
% pip install --upgrade pip uv
% uv venv
% uv sync --all-groups
% bun install
```

Link up a settings file (you'll need to create the postgres db first, username: 'ureport' password: 'nyaruka')
```
% ln -s ureport/settings.py.postgres ureport/settings.py
```

Sync the database, add all our models and create our superuser
```
% python manage.py syncdb
% python manage.py migrate
% python manage createsuper
% python manage collectstatic
```

At this point everything should be good to go, you can start with:

```
% python manage.py runserver
```

Note that the endpoint called for API calls is by default 'localhost:8001', you can uncomment the RAPIDPRO_API line in settings.py.postgres to go against production servers.

## Running with Docker

The repository ships a `Dockerfile` that builds a single image serving all the
process types — static assets are collected and offline-compressed into the
image, and all deployment configuration comes from environment variables (see
`ureport/settings.py.docker`). The web process is the default command; workers
and the beat scheduler run from the same image:

```
% gunicorn ureport.wsgi:application            # default CMD
% celery -A ureport worker -Q sync -Ofair      # a queue worker
% celery -A ureport beat                       # the scheduler (safe to run replicas)
```

Required environment: `DJANGO_SECRET_KEY`, `DATABASE_URL` and `VALKEY_HOST` (or
`VALKEY_URL`). See `ureport/settings.py.docker` for the optional settings
(hostnames, email, object storage, security toggles).

For a local containerized stack:

```
% docker compose up --build
% docker compose exec web python manage.py migrate
% docker compose exec web python manage.py createsuperuser
```
