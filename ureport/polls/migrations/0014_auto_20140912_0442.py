# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    def move_images(apps, schema_editor):
        # for each poll we want to move any image currently on it and instead create a PollImage for it
        Poll = apps.get_model("polls", "Poll")
        PollImage = apps.get_model("polls", "PollImage")

        for poll in Poll.objects.exclude(image=None):
            PollImage.objects.create(
                poll=poll, image=poll.image, created_by=poll.created_by, modified_by=poll.modified_by
            )

    dependencies = [("polls", "0013_pollimage")]

    operations = [migrations.RunPython(move_images)]
