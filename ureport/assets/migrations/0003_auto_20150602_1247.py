# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("assets", "0002_populate_images")]

    operations = [
        migrations.AlterField(
            model_name="image",
            name="image_type",
            field=models.CharField(
                default="P",
                max_length=1,
                verbose_name="Image type",
                choices=[("B", "Banner"), ("P", "Pattern"), ("F", "Flag")],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="image",
            name="name",
            field=models.CharField(
                help_text="A short descriptive name for this image", max_length=128, verbose_name="Name"
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="image",
            name="org",
            field=models.ForeignKey(
                related_name="images",
                on_delete=models.PROTECT,
                verbose_name="Org",
                to="orgs.Org",
                help_text="The organization to which the image will be used",
            ),
            preserve_default=True,
        ),
    ]
