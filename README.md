U-report  
=========

[![Build Status][master-build-image]][travis-ci]

[travis-ci]: https://travis-ci.org/rapidpro/ureport/
[master-build-image]: https://travis-ci.org/rapidpro/ureport.svg?branch=master

This is the U-report dashboard built on data collected by RapidPro.

Built for UNICEF by Nyaruka - http://nyaruka.com

Getting Started
================

Install dependencies
```
% virtualenv env
% source env/bin/activate
% pip install -r pip-freeze.txt
```

Link up a settings file (you'll need to create the postgres db first, username: 'ureport' password: 'nyaruka')
```
% cp ureport/settings.py.postgres ureport/settings.py
```

Sync the database, add all our models and create our superuser
```
% python manage.py syncdb
% python manage.py migrate
% python manage createsuper
```

At this point everything should be good to go, you can start with:

```
% python manage.py runserver
```

Note that the endpoint called for API calls is by default 'localhost:8001', you can uncomment the RAPIDPRO_API line in settings.py.postgres to go against production servers.
