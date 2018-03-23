# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import *

import json
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.translation import ugettext_lazy as _

from django_countries import countries
import git
import os
from ureport.countries.models import CountryAlias


class Command(BaseCommand):
    help = 'Add countries alias from the json files at https://github.com/umpirsky/country-list/tree/master/country'

    def import_file(self, json_file, user):
        countries_json = json.loads(json_file.read())
        all_countries_codes = countries.countries

        for country in countries_json:
            name = countries_json.get(country, None)
            country = country.upper()
            if name and country in all_countries_codes:
                CountryAlias.get_or_create(country, name, user)

    def handle(self, *args, **options):

        if os.path.exists('./country-list/') and os.path.isdir('./country-list'):
            print("Fetching country-list...")
            os.chdir('./country-list')
            repo = git.Repo('.')
            o = repo.remotes.origin
            o.pull()
            os.chdir('..')
            print("Finished fetching country-list.")
        else:
            print("Cloning country-list...")
            git.Git().clone('https://github.com/umpirsky/country-list.git', 'country-list')
            print("Finished cloning country-list.")

        print("Looking up json files...")

        filenames = []

        i = 0
        for path, subdirs, files in os.walk('./country-list/country/'):
            for name in files:
                if name.endswith('.json'):
                    filenames.append(os.path.join(path, name))
                    print("Found %s" % os.path.join(path, name))
                    i += 1

        print("Found %d json files to parse")

        user = User.objects.filter(username="root").first()

        if not user:
            raise Exception(_("No root user found. Please create a root user"))

        print("Parsing files...")
        for filename in filenames:
            print("Parsing file %s" % filename)
            with open(filename) as json_file:
                self.import_file(json_file, user)

        print("All files parsed.")
