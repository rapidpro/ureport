# Generated by Django 2.0.9 on 2018-11-12 14:03

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('policies', '0002_auto_20181112_1359'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='policy',
            name='org',
        ),
    ]
