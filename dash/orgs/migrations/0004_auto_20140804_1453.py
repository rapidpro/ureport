# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0003_org_logo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='org',
            name='administrators',
            field=models.ManyToManyField(help_text='The administrators in your organization', to=settings.AUTH_USER_MODEL, verbose_name='Administrators'),
        ),
        migrations.AlterField(
            model_name='org',
            name='editors',
            field=models.ManyToManyField(help_text='The editors in your organization', to=settings.AUTH_USER_MODEL, verbose_name='Editors'),
        ),
        migrations.AlterField(
            model_name='org',
            name='viewers',
            field=models.ManyToManyField(help_text='The viewers in your organization', to=settings.AUTH_USER_MODEL, verbose_name='Viewers'),
        ),
    ]
