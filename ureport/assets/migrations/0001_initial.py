# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('orgs', '0008_org_timezone'),
    ]

    operations = [
        migrations.CreateModel(
            name='Image',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_active', models.BooleanField(default=True, help_text=b'Whether this item is active, use this instead of deleting')),
                ('created_on', models.DateTimeField(help_text=b'When this item was originally created', auto_now_add=True)),
                ('modified_on', models.DateTimeField(help_text=b'When this item was last modified', auto_now=True)),
                ('name', models.CharField(help_text='The name to describe this background', max_length=128, verbose_name='Name')),
                ('image_type', models.CharField(default='P', max_length=1, verbose_name='Background type', choices=[('B', 'Banner'), ('P', 'Pattern')])),
                ('image', models.ImageField(help_text='The image file', upload_to='images')),
                ('created_by', models.ForeignKey(related_name='assets_image_creations', to=settings.AUTH_USER_MODEL, help_text=b'The user which originally created this item')),
                ('modified_by', models.ForeignKey(related_name='assets_image_modifications', to=settings.AUTH_USER_MODEL, help_text=b'The user which last modified this item')),
                ('org', models.ForeignKey(related_name='images', verbose_name='Org', to='orgs.Org', help_text='The organization in which the image will be used')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
    ]
