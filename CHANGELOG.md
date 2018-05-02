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

