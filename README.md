dash 
====

Dashboard framework for TextIt apps

Getting Started
================

* Install dependencies
```
% virtualenv env
% source env/bin/activate
% pip install -r pip-requires.txt
```

* Link up a settings file (you'll need to create the postgres db first, username: 'ureport' password: 'nyaruka')
```
% ln -s ureport/settings.py.postgres ureport/settings.py
```

* Sync the database, add all our models and create our superuser
```
% python manage.py syncdb
% python manage.py migrate
% python manage createsuper
```

At this point everything should be good to go, you can start with:

```
% python manage.py runserver
```
