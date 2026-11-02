from django.db import migrations

from ureport.sql import InstallSQL


class Migration(migrations.Migration):

    dependencies = [
        ("polls", "0081_install_triggers"),
    ]

    operations = [InstallSQL("polls_0082")]
