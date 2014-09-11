# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('categories', '0002_auto_20140820_1415'),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoryImage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_active', models.BooleanField(default=True, help_text=b'Whether this item is active, use this instead of deleting')),
                ('created_on', models.DateTimeField(help_text=b'When this item was originally created', auto_now_add=True)),
                ('modified_on', models.DateTimeField(help_text=b'When this item was last modified', auto_now=True)),
                ('name', models.CharField(help_text=b'The name to describe this image', max_length=64)),
                ('image', models.ImageField(help_text='The image file to use', upload_to=b'categories')),
                ('category', models.ForeignKey(help_text=b'The category this image represents', to='categories.Category')),
                ('created_by', models.ForeignKey(help_text=b'The user which originally created this item', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(help_text=b'The user which last modified this item', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
    ]
