# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import urllib

from django.db import models, migrations
from django.core.files.images import ImageFile


def populate_images(apps, schema_editor):
    OrgBackground = apps.get_model('orgs', "OrgBackground")
    Image = apps.get_model('assets', "Image")

    for org_bg in OrgBackground.objects.all():
        image_file = None
        try:
            image_file = open(org_bg.image.path, 'rb')
        except NotImplementedError:
            retrived_image = urllib.urlretrieve(org_bg.image.url)
            image_file = open(retrived_image[0])
        except IOError:
            pass

        finally:
            if image_file:
                django_image_file = ImageFile(image_file)
                image_filename = org_bg.image.path.split('/')[-1]

                image_obj = Image()
                image_obj.org = org_bg.org
                image_obj.name = org_bg.name
                image_obj.image_type = org_bg.background_type
                image_obj.is_active = org_bg.is_active
                image_obj.created_by = org_bg.created_by
                image_obj.modified_by = org_bg.modified_by
                image_obj.image.save(image_filename, django_image_file, save=True)


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(populate_images),
    ]
