# Generated by Django 4.2.6 on 2023-10-25 09:13

from django.db import migrations


def noop(apps, schema_editor):  # pragma: no cover
    pass


def populate_poll_published(apps, schema_editor):  # pragma: no cover
    Poll = apps.get_model("polls", "Poll")

    # copy is_active to published
    Poll.objects.filter(is_active=False).update(published=False)

    # make all poll have is_active=True
    Poll.objects.filter(is_active=False).exclude(flow_uuid="").update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("polls", "0074_poll_published"),
    ]

    operations = [migrations.RunPython(populate_poll_published, noop)]
