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

