# Generated by Django 3.2.6 on 2021-09-13 10:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0014_contactactivity_scheme"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchemeSegment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scheme", models.CharField(max_length=16, unique=True)),
            ],
        ),
    ]