# U-Report 

[![Build Status](https://github.com/rapidpro/ureport/workflows/CI/badge.svg)](https://github.com/rapidpro/ureport/actions?query=workflow%3ACI) 
[![codecov](https://codecov.io/gh/rapidpro/ureport/branch/main/graph/badge.svg)](https://codecov.io/gh/rapidpro/ureport)

This is the U-Report dashboard built on data collected by RapidPro.

Built for UNICEF by Nyaruka - http://nyaruka.com

Getting Started
================

Install dependencies
```
% pip install --upgrade pip poetry
% poetry install --no-root
% poetry shell
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

## GitHub Copilot Setup

For an enhanced development experience with GitHub Copilot, see our [Copilot Setup Guide](COPILOT_SETUP.md).
