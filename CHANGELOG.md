v1.0.457
----------
 * Merge pull request #415 from rapidpro/fix-global-locations-data
 * Fix coverage
 * Change World geojson data
 * Merge pull request #414 from Ilhasoft/feature/flagsupdate
 * Fix "test_get_linked_orgs".
 * Added Honduras, Iraq and removed U.K. flags.
 * Merge pull request #83 from rapidpro/master

v1.0.456
----------
 * Rerun compilemessages and makemessages
 * Fix poll response categories to be deactivated if they are replaced

v1.0.455
----------
 * Merge pull request #411 from rapidpro/dependabot/pip/django-2.1.9
 * Bump django from 2.1.5 to 2.1.9

v1.0.454
----------
 * Add Bolivia and Ecuador flags on the footer

v1.0.453
----------
 * Add India flag on the footer

v1.0.452
----------
 * Merge pull request #409 from rapidpro/no-flow-def-use
 * Use flow results metada for all poll flows

v1.0.451
----------
 * Update rapidpro-python to 2.6.1

v1.0.450
----------
 * Make flow metadate node uuids optional

v1.0.449
----------
 * Merge pull request #408 from rapidpro/use-flow-metadata
 * Update the rapidpro client
 * Use the metadata only for flows that do not have rulesets on the definition
 * Use flow results metadata to create questions and their categories
 * Merge pull request #407 from rapidpro/verify-locales
 * update uz locale file
 * fix warnings, update locale files, set up travis to catch errors / missing rebuilds
 * Update CHANGELOG.md for v1.0.448
 * Increase contact pull lock timeout to 12 hours

v1.0.448
----------
 * Increase contact pull lock timeout to 12 hours

v1.0.447
----------
 * Merge pull request #405 from rapidpro/ureport-v2-1
 * Add missing file
 * Disable some tests temporaly
 * Add /v2 urls for public site, site under construction page
 * Merge pull request #403 from Ilhasoft/fix/error-pages
 * Change U-Report Logo
 * Merge pull request #79 from rapidpro/master
 * Merge pull request #402 from Ilhasoft/hotfix/news-date
 * Fix tests to support new date format localized
 * Fix spacing between imports and code
 * Refactor created date for News by using the localization to format it
 * Merge pull request #78 from rapidpro/master
 * Merge pull request #76 from rapidpro/master

v1.0.446
----------
 * Update FB customerchat plugin SDK
 * Refactor Serbian Latin translation files
 * Add romanian translation files updates
 * Refactor serbian to serbian latin language config
 * Fix unordered list

v1.0.445
----------
 * Polls without flow uuid should not sync
 * Run tests on Postgresql9.6 and Postgresql10

v1.0.444
----------
 * Update Django
 * Update deps

v1.0.443
----------
 * Add Romania flag
 * Remove opacity on map legend

v1.0.442
----------
 * Add locations stats to poll API endpoint
 * Update pt_br strings translations

v1.0.441
----------
 * Add Serbia flag, update settings
 

v1.0.440
----------
 * Merge pull request #385 from rapidpro/age-category-case
 * Keep category case for age  seggments

v1.0.439
----------
 * Pin django to 2.0.9
 * Update tests
 * Change scale label to use ALL instead of National
 * Update django
 * Add config to control the states we render on the maps
 * Add results grouped by gender and by age to the API

v1.0.438
----------
 * Refactor strings on bosnian files
 * Add bosnia country flag

v1.0.437
----------
 * Add bosnian language option
 * Fix assertion for the country order
 * Add uzbekistan logo
 * Update Trinidad and Tobago flag
 * Add uzbek language

v1.0.436
----------
 * No response case has a datetime in value, we should not consider that as text if we did not have an input

v1.0.435
----------
 * Do not show ignored words on word clouds

v1.0.434
----------
 * Support Django 2.0

v1.0.432
----------
 * Merge pull request #377 from rapidpro/specific-category-order
 * Fix Facebook page embed without facebook appId
 * Fix Facebook page embed without facebook appId
 * Fix poll questions category order
 * Merge pull request #376 from rapidpro/pip-tools

v1.0.425
----------
 * Merge pull request #375 from rapidpro/fix-RSS-jobs
 * Fix RSS feed jobs summary look up

v1.0.424
----------
 * Merge pull request #372 from rapidpro/use-archives
 * Merge pull request #373 from rapidpro/brasil-count
 * upadate link for Brasil count

v1.0.421
----------
 * Merge pull request #371 from Ilhasoft/feature/new-flags
 * Fix flags ordering
 * Add Bangladesh logo
 * Add new country flags
 * Merge pull request #57 from rapidpro/master
 * Merge pull request #368 from Ilhasoft/feature/charts-ordering
 * Merge pull request #366 from Ilhasoft/hotfix/org-lang
 * Add new entry to test org lang
 * Add order by created on desc on recent polls
 * Fix org lang context variable setting
 * Merge pull request #55 from rapidpro/master
 * Merge pull request #54 from rapidpro/master

v1.0.420
----------
 * Merge pull request #369 from rapidpro/map-colors
 * Add config for custom maps colors

v1.0.419
----------
 * Add config for announcement

v1.0.418
----------
 * Fix bug, no response should not be considered as responded

v1.0.417
----------
 * Strip trailing spaces on ignore words

v1.0.416
----------
 * Switch to use Summernote JS library for text editor

v1.0.413
----------
 * Merge pull request #362 from rapidpro/ignore-words
 * Add config for ignore words to filter out on the public page

v1.0.412
----------
 * Merge pull request #361 from rapidpro/hide-participations
 * Add config to hide participations stats

v1.0.411
----------
 * Merge pull request #359 from Ilhasoft/balkans-flag
 * Merge pull request #358 from Ilhasoft/feature/facebook-welcome-message
 * Fix org config fields by incrementing fields on superuser test
 * Fix linked orgs tests because of new flag included on the bottom
 * Fix org config fields tests by incrementing the new field created
 * Add western balkans on the bottom of the page
 * Add welcome text to the template when it does exist
 * Add new config field for welcome message on Facebook plugin
 * Merge pull request #52 from rapidpro/master
 * Merge pull request #51 from rapidpro/master
 * Merge pull request #50 from rapidpro/master
 * Merge pull request #49 from rapidpro/master

v1.0.410
----------
 * Support FLOIP backend type
 * Switch to Python3

v1.0.408
----------
 * Remove attribution attribute

v1.0.407
----------
 * Fix syntax

v1.0.406
----------
 * Use latest FB SDK version

v1.0.405
----------
 * More HTTPS use

v1.0.404
----------
 * Add FB messenger customer chat plugin

v1.0.403
----------
 * Fix for None values and datetime type in the recent changes

v1.0.402
----------
 * Update rapidpro-dash
 * Trim poll results long text values
 * Specify the backend attr on the syncers
 * Use remote contact created on if the registered on value in None

v1.0.401
----------
 * Fix to display age charts
 * Default value for fetch_flows for the cache miss should be an empty dict

v1.0.400
----------
 * Default value for fetch_flows for the cache miss should be an empty dict

v1.0.399
----------
 * Only exclude the main poll if we have one

v1.0.398
----------
 * Make sure tasks do no sync polls synced by other tasks that run more often

v1.0.397
----------
 * Fix get_flow and enable the cached times in contacts pull

v1.0.396
----------
 * Hold on to use redis cache times for contacts sycn until we have some values set
 * Add backend fields as Foreign keys
 * Use .paths to set and retrieve Org config values 

v1.0.393
----------
 * Update test

v1.0.392
----------
 * Fix poll brick ids

v1.0.391
----------


v1.0.389
----------
 * Remove unused function
 * Remove unecessary configs
 * Switch to use rapidpro config
 * Update to use latest pillow and boto3

v1.0.388
----------
 * Do not add backend field on poll results

v1.0.387
----------
* Fix import
 * Better log
 * Update pull results default value in batches

v1.0.386
----------
 * Add default value and constraints migrations
 * Faster migrations

v1.0.385
----------
 * Add backend field
 * Update dash to 1.3.1
 * Fix test
 * Contacts pull should loop on all configured backends

v1.0.383
----------
 * Add argentina flag to settings
 * Fix tests
 * Fix PEP8 errors

v1.0.382
----------
 * Update sorl-thumbnail to mute unecessary logs 

v1.0.379
----------
 * Update sorl-thumbnail and more deps

v1.0.377
----------
 * Fix inexistent key lookup, and Add DB slice config

v1.0.372
----------
 * Add TEMPLATE_DEBUG settings

v1.0.371
----------
 * Update deps

v1.0.370
----------
 * update gitignore
 * Merge pull request #330 from rapidpro/fix-registration-map-month
 * Better month lookup from date

v1.0.369
----------
 * Rebuild poll results counts only when we have new or updated poll results

v1.0.368
----------
 * Fix poll admin list styles

v1.0.367
----------
 * Make sure we handle properly the rate error in the batch syncs too

v1.0.366
----------
 * Add tests
 * Ignore Rate limit exception since we'll resume the next hour

v1.0.365
----------
 * More coverage and remove duplicate tests
 * Use django cache methods and update tests
 * Use redis to record the last time a poll synced for long running poll sync tasks

v1.0.364
----------
 * Prevent timeout trying to check the progress while we know we synced at least once

v1.0.363
----------
 * Display read only org config fields
 * Display last sync times using timesince

v1.0.359
----------
 * Add Moldova flag to footer
 * Remove unused codes

v1.0.358
----------
 * Fix contacts sync

v1.0.357
----------
 * Use the leaf to lookup location object in a simple way as usual
 * Support consuming datetimes in iso8601 format

v1.0.356
----------
 * Fix small text fonts
 * Allow configuring of custom fonts

v1.0.355
----------
 * Fix height of map to prevent overflow
 * Update Spanish
 * Add Vietnamese

v1.0.354
----------
 * Update message on homepage

v1.0.353
----------
 * Filter by is_active too to consider similar poll
 * Limit the creation of polls to 1 per flow in 5 minutes
 * Fix Zambia count link

v1.0.352
----------
 * Update the rapidpro client to support flow minor versions

v1.0.351
----------
 * Update to use better names
 * Make all recent polls sync every hour

v1.0.350
----------
 * Add New Zealand
 * Add romanian language

v1.0.349
----------
  * Mark sync poll result paused before the lock times out
  * Increase lock timeout for poll pull results

v1.0.348
----------
 * Update smartmin
 * Refactor pull results to shorter size methods

v1.0.347
----------
 * Update fix for pycountry update

v1.0.346
----------
 * Update all deps to the latests

v1.0.345
----------
 * Update django-storages

v1.0.344
----------
 * Use big int for poll results counter primary key, migrations
 * Update dependencies

v1.0.343
----------
 * Merge pull request #293 from rapidpro/result-text-field

v1.0.341
----------
 * More italian
 * Display only featured stories on home page

v1.0.340
----------
 * Update Italian

v1.0.339
----------
 * Add El Salvador

v1.0.338
----------
 * Update translations

v1.0.336
----------
 * Fix refetch poll on big orgs

v1.0.335
----------
 * Fix flow definition lookup from flow definition endpoint using the right uuid

v1.0.334
----------
 * Remove all use of API v1

v1.0.333
----------
 * Reschedule poll pull task in 5 min if pull did not finish

v1.0.332
----------
 * Fix get boundaries
 * Update Arabic language

v1.0.331
----------
 * More fix for remote missing geometry

v1.0.330
----------
 * Fix building global boundaries and boundary missing geometry

v1.0.329
----------
 * Switch locations sync to use RapidPro API v2
 * Ordering open ended words cloud responses first then limit the list to 100

v1.0.328
----------
 * Update ukrainian translations

v1.0.327
----------
 * Change story widget URL to https

v1.0.326
----------
 * Add migrations to remove inactive objects not needed
 * FIx typo in method name for syncers

v1.0.325
----------
 * Tweak date styles

v1.0.324
----------
 * Add Facebook message us button on home page
 * Add story date
 * Make all script load on https

v1.0.323
----------
* remove escape on news link text

v1.0.322
----------
 * Add CHANGELOG.md
 * AWS S3 secure urls

