# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Invitation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_active', models.BooleanField(default=True, help_text=b'Whether this item is active, use this instead of deleting')),
                ('created_on', models.DateTimeField(help_text=b'When this item was originally created', auto_now_add=True)),
                ('modified_on', models.DateTimeField(help_text=b'When this item was last modified', auto_now=True)),
                ('email', models.EmailField(help_text='The email to which we send the invitation of the viewer', max_length=75, verbose_name='Email')),
                ('secret', models.CharField(help_text='a unique code associated with this invitation', unique=True, max_length=64, verbose_name='Secret')),
                ('user_group', models.CharField(default=b'V', max_length=1, verbose_name='User Role', choices=[(b'A', 'Administrator'), (b'E', 'Editor'), (b'V', 'Viewer')])),
                ('created_by', models.ForeignKey(help_text=b'The user which originally created this item', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(help_text=b'The user which last modified this item', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Org',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_active', models.BooleanField(default=True, help_text=b'Whether this item is active, use this instead of deleting')),
                ('created_on', models.DateTimeField(help_text=b'When this item was originally created', auto_now_add=True)),
                ('modified_on', models.DateTimeField(help_text=b'When this item was last modified', auto_now=True)),
                ('name', models.CharField(help_text='The name of this organization', max_length=128, verbose_name='Name')),
                ('language', models.CharField(choices=[(b'en-us', b'English'), (b'rw', b'Kinyarwanda'), (b'fr', b'French')], max_length=64, blank=True, help_text='The main language used by this organization', null=True, verbose_name='Language')),
                ('subdomain', models.SlugField(error_messages={b'unique': 'This subdomain is not available'}, max_length=255, help_text='The subdomain for this UReport instance', unique=True, verbose_name='Subdomain')),
                ('api_token', models.CharField(help_text='The API token for the RapidPro account this dashboard is tied to', max_length=128, null=True, blank=True)),
                ('config', models.TextField(help_text='JSON blob used to store configuration information associated with this organization', null=True, blank=True)),
                ('administrators', models.ManyToManyField(to=settings.AUTH_USER_MODEL, verbose_name='Administrators')),
                ('created_by', models.ForeignKey(help_text=b'The user which originally created this item', to=settings.AUTH_USER_MODEL)),
                ('editors', models.ManyToManyField(to=settings.AUTH_USER_MODEL, verbose_name='Editors')),
                ('modified_by', models.ForeignKey(help_text=b'The user which last modified this item', to=settings.AUTH_USER_MODEL)),
                ('viewers', models.ManyToManyField(to=settings.AUTH_USER_MODEL, verbose_name='Viewers')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='invitation',
            name='org',
            field=models.ForeignKey(verbose_name='Org', to='orgs.Org', help_text='The organization to which the account is invited to view'),
            preserve_default=True,
        ),
    ]
