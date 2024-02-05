# U-Report 

[![Build Status](https://github.com/rapidpro/ureport/workflows/CI/badge.svg)](https://github.com/rapidpro/ureport/actions?query=workflow%3ACI) 
[![codecov](https://codecov.io/gh/rapidpro/ureport/branch/main/graph/badge.svg)](https://codecov.io/gh/rapidpro/ureport)

This is the U-Report dashboard built on data collected by RapidPro.

Built for UNICEF by Nyaruka - http://nyaruka.com

Getting Started
================

Install dependencies
```
$ curl -sSL https://install.python-poetry.org | python3 - --version 1.6.1
$ poetry install --no-root
$ poetry shell
$ sudo apt-get install gettext
```

Create a settings file (you'll need to create the postgres db first, username: 'ureport' password: 'nyaruka')
```
$ cp ureport/settings.py.postgres ureport/settings.py
```

Sync the database, add all our models and create our superuser
```
$ sudo service postgresql start

$ sudo -u postgres psql

CREATE USER ureport WITH PASSWORD 'nyaruka';
CREATE DATABASE ureport;
GRANT ALL PRIVILEGES ON DATABASE ureport TO ureport;
\q
```

```
$ python manage.py migrate
$ python manage.py createsuperuser
$ python manage.py collectstatic
```

At this point everything should be good to go, you can start with:

```
$ python manage.py runserver
```

Note that the endpoint called for API calls is by default 'localhost:8001', you can uncomment the RAPIDPRO_API line in settings.py.postgres to go against production servers.
