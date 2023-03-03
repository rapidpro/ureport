# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import os

import git
from django_countries import countries

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _

from ureport.countries.models import CountryAlias

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Add countries alias from the json files at https://github.com/umpirsky/country-list/tree/master/country"

    def import_file(self, json_file, user):
        countries_json = json.loads(json_file.read())
        all_countries_codes = countries.countries

        for country in countries_json:
            name = countries_json.get(country, None)
            country = country.upper()
            if name and country in all_countries_codes:
                CountryAlias.get_or_create(country, name, user)

    def handle(self, *args, **options):
        if os.path.exists("./country-list/") and os.path.isdir("./country-list"):
            logger.info("Fetching country-list...")
            os.chdir("./country-list")
            repo = git.Repo(".")
            o = repo.remotes.origin
            o.pull()
            os.chdir("..")
            logger.info("Finished fetching country-list.")
        else:
            logger.info("Cloning country-list...")
            git.Git().clone("https://github.com/umpirsky/country-list.git", "country-list")
            logger.info("Finished cloning country-list.")

        logger.info("Looking up json files...")

        filenames = []

        i = 0
        for path, subdirs, files in os.walk("./country-list/country/"):
            for name in files:
                if name.endswith(".json"):
                    filenames.append(os.path.join(path, name))
                    logger.info("Found %s" % os.path.join(path, name))
                    i += 1

        logger.info("Found %d json files to parse")

        user = User.objects.filter(username="root").first()

        if not user:
            raise Exception(_("No root user found. Please create a root user"))

        logger.info("Parsing files...")
        for filename in filenames:
            logger.info("Parsing file %s" % filename)
            with open(filename, encoding="utf-8") as json_file:
                self.import_file(json_file, user)

        logger.info("All files parsed.")
