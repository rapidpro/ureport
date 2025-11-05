v1.2.169 (2025-10-31)
-------------------------
 * Reduce squash items query rows
 * Use batch size for bulk create

v1.2.168 (2025-10-31)
-------------------------
 * Loop on all objects to insert
 * Use queryset iterator for getting reporters counts

v1.2.167 (2025-10-30)
-------------------------
 * Remove no longer needed periodic task schedule
 * Remove use of list for all contacts
 * Run code_checks
 * Use iterator for large querysets

v1.2.166 (2025-10-29)
-------------------------
 * Merge pull request #1292 from rapidpro/insert_batches
 * Insert poll stats using batch size with bulk create

v1.2.165 (2025-10-29)
-------------------------
 * Merge pull request #1291 from rapidpro/reduce-db-load
 * Merge pull request #1289 from rapidpro/fcm-display
 * Stop updting past results on contact sync
 * Add ureport app links to join page

v1.2.164 (2025-10-28)
-------------------------
 * Merge pull request #1290 from rapidpro/reduce-db-load-1
 * Fix date

v1.2.162 (2025-10-10)
-------------------------
 * Merge pull request #1286 from rapidpro/update-rp-client
 * Update rapidpro-client

v1.2.161 (2025-10-07)
-------------------------
 * Merge pull request #1285 from rapidpro/validate-slug-landing-page
 * Allow hyphens in landing pages slug
 * Update django
 * Validate landing pages slug

v1.2.160 (2025-09-10)
-------------------------
 * Merge pull request #1284 from rapidpro/updates
 * Update django
 * Merge pull request #1282 from rapidpro/dependabot/pip/urllib3-2.5.0
 * Bump urllib3 from 2.3.0 to 2.5.0

v1.2.159 (2025-06-17)
-------------------------
 * Merge pull request #1279 from rapidpro/more-valkey

v1.2.157 (2025-06-17)
-------------------------
 * Merge pull request #1277 from rapidpro/django_valkey

v1.2.155 (2025-06-12)
-------------------------
 * Merge pull request #1276 from rapidpro/updates
 * Update archive type param
 * Update deps
 * Merge pull request #1275 from rapidpro/dependabot/pip/django-5.2.2
 * Merge pull request #1274 from rapidpro/dependabot/pip/requests-2.32.4
 * Bump django from 5.2.1 to 5.2.2
 * Bump requests from 2.32.3 to 2.32.4

v1.2.154 (2025-06-03)
-------------------------
 * Merge pull request #1273 from rapidpro/gtm-check

v1.2.152 (2025-05-21)
-------------------------
 * Merge pull request #1272 from rapidpro/add-eth
 * Add ETH to dropdown

v1.2.151 (2025-05-19)
-------------------------
 * Merge pull request #1271 from rapidpro/update-django
 * Update to support django 5.2

v1.2.150 (2025-04-04)
-------------------------
 * Merge pull request #1264 from rapidpro/custom-html
 * Add custom_html config to the public pages

v1.2.149 (2025-04-01)
-------------------------
 * Merge pull request #1270 from rapidpro/add-aus
 * Add AUS link to countries dropdown

v1.2.148 (2025-03-26)
-------------------------
 * Merge pull request #1269 from rapidpro/translations_locale-en-lc-messages-django-po--main_es
 * Run code checks
 * Translate locale/en/LC_MESSAGES/django.po in es

v1.2.147 (2025-02-25)
-------------------------
 * Adjust categories labels and displays labels

v1.2.145 (2025-02-24)
-------------------------
 * Update locales
 * Run test on latest ubuntu
 * Run code checks
 * Update deps
 * Remove csv_imports

v1.2.144 (2025-02-21)
-------------------------
 * Fix logout button to use POST method
 * Update GH action to use postgress image on CI
 * Update pyproject.toml for poetry 2

v1.2.143 (2025-01-06)
-------------------------
 * Merge pull request #1260 from rapidpro/poll-results-big-int
 * Change poll result id to big int

v1.2.142 (2025-01-02)
-------------------------
 * Update Brasil host url

v1.2.141 (2024-12-19)
-------------------------
 * Fix set

v1.2.140 (2024-12-18)
-------------------------
 * Merge pull request #1258 from rapidpro/fix-clearing-results
 * Prevent clearing results for polls with the same flow

v1.2.139 (2024-12-12)
-------------------------
 * Merge pull request #1255 from rapidpro/sync-paths-no-time
 * Sync results from paths without time

v1.2.138 (2024-12-10)
-------------------------
 * Merge pull request #1257 from rapidpro/dependabot/pip/django-5.1.4
 * Bump django from 5.1.2 to 5.1.4
 * Merge pull request #1256 from rapidpro/malawi-site-fix
 * Fix Malawi site domain

v1.2.137 (2024-12-04)
-------------------------
 * Merge pull request #1254 from rapidpro/custom-stories-link
 * Merge pull request #1253 from rapidpro/comment-sync
 * Merge pull request #1240 from rapidpro/cleanup-used-files
 * Add external stories link support in config
 * Add comment to results sync
 * Merge pull request #1252 from rapidpro/update-rapidpro-client
 * Update rapidpro python client to 2.16.0
 * Cleanup old unused files

v1.2.136 (2024-10-24)
-------------------------
 * Merge pull request #1249 from rapidpro/update-python

v1.2.134 (2024-10-23)
-------------------------
 * Update deps
 * Support django 5.1
 * Adjust old migrations to not use index_together
 * Use GH actions services for Redis and Postgres

v1.2.133 (2024-09-26)
-------------------------
 * Add lock to run the contacts activities squash once

v1.2.132 (2024-09-24)
-------------------------
 * Squash contacts activities counts every 15min
 * Run code checks
 * Translate locale/en/LC_MESSAGES/django.po in cs

v1.2.131 (2024-09-18)
-------------------------
 * Set the max length for poll result text
 * Do not sync empty contacts not having URNs set

v1.2.130 (2024-08-28)
-------------------------
 * Merge pull request #1239 from rapidpro/extra-menu
 * Use extra menu link config for global site

v1.2.129 (2024-08-28)
-------------------------
 * Merge pull request #1236 from rapidpro/extra-menu
 * Merge pull request #1238 from rapidpro/add-dominicana
 * Fix name
 * Add support for extra link on menu

v1.2.128 (2024-08-28)
-------------------------
 * Merge pull request #1237 from rapidpro/add-dominicana
 * Merge pull request #1235 from rapidpro/fix-index-together-unique-toghether-use
 * Add Dominicana link
 * Merge pull request #1233 from rapidpro/updates
 * Adjust indexes and constraints
 * Update deps
 * Merge pull request #1231 from rapidpro/update-deps
 * Update sentry-sdk
 * Update deps
 * Reduce size of logo images to load faster on pages

v1.2.127 (2024-07-26)
-------------------------
 * Merge pull request #1229 from rapidpro/kazakh-unicef-logo
 * Adjust UNICEF logo for Kazakh
 * Merge pull request #1228 from rapidpro/update_dash
 * Update dash to order admins on org forms

v1.2.126 (2024-07-12)
-------------------------
 * Merge pull request #1227 from rapidpro/add-kazakhstan
 * Add Kazakhstan

v1.2.125 (2024-07-11)
-------------------------
 * Merge pull request #1226 from rapidpro/update-deps
 * Update JS deps
 * Merge pull request #1225 from rapidpro/update-deps
 * Run code checks
 * Update deps

v1.2.124 (2024-07-09)
-------------------------
 * Merge pull request #1223 from rapidpro/kaz-updates
 * Fix type for Macedonia
 * Update KK translations

v1.2.123 (2024-07-02)
-------------------------
 * Merge pull request #1222 from rapidpro/use-py-3.11

v1.2.119 (2024-06-28)
-------------------------
 * Merge pull request #1220 from rapidpro/GA4
 * Merge pull request #1221 from rapidpro/fix-polls-queries-for-sync
 * Make sure polls with inactive category are hidden from the public
 * Support GA4 measurement ID
 * fix queries for polls used to sync results to always sync polls even if there categories are inactive

v1.2.118 (2024-06-06)
-------------------------
 * Merge pull request #1219 from rapidpro/add-kazakh
 * Add Kazakh

v1.2.117 (2024-05-29)
-------------------------
 * Fix extra spaces typo

v1.2.116 (2024-05-24)
-------------------------
 * Merge pull request #1218 from rapidpro/support-IG-deeplinks
 * Add config for Instagram deeplink checkbox

v1.2.115 (2024-05-23)
-------------------------
 * Merge pull request #1214 from rapidpro/support-IG-deeplinks
 * Run poetry lock
 * Add Instagram deeplink on join page
 * Merge pull request #1212 from rapidpro/update-CI-actions
 * Update Github actions to latest versions

v1.2.114 (2024-05-02)
-------------------------
 * Merge pull request #1210 from rapidpro/fix-homepage-poll-bg-color-new-brand

v1.2.112 (2024-04-17)
-------------------------
 * Merge pull request #1209 from rapidpro/fix-stories-api
 * Run code checks
 * Fix stories API queryset
 * Merge pull request #1208 from rapidpro/update-deps
 * Update deps
 * Merge pull request #1207 from rapidpro/update-deps
 * Update deps
 * Merge pull request #1206 from rapidpro/dependabot/pip/gunicorn-22.0.0
 * Bump gunicorn from 20.1.0 to 22.0.0

v1.2.111 (2024-04-16)
-------------------------
 * Merge pull request #1205 from rapidpro/update-depsss
 * Run poetry lock
 * Run poetry lock
 * Test on Django 5.0.x only
 * Merge pull request #1202 from Ilhasoft/fix/check-new-brand-in-rtl-orgs
 * Check new brand in RTL organizations

v1.2.110 (2024-04-16)
-------------------------
 * Merge pull request #1201 from rapidpro/fix-drf-base-template

v1.2.108 (2024-04-11)
-------------------------
 * Merge pull request #1200 from rapidpro/message-storage-sessions

v1.2.106 (2024-04-11)
-------------------------
 * Merge pull request #1199 from rapidpro/update-js-libraries

v1.2.104 (2024-04-11)
-------------------------
 * Merge pull request #1198 from rapidpro/error-page

v1.2.102 (2024-04-09)
-------------------------
 * Update FB JS SDK versions
 * Merge pull request #1171 from rapidpro/prep-django5
 * Update DRF to 3.15.0
 * Use datetime timezone aliased as tzone
 * Prep and start testing on django 5.0
 * Merge pull request #1196 from rapidpro/update-deps
 * Update django
 * Update to latest black, ruff, isort and djlint

v1.2.101 (2024-03-05)
-------------------------
 * Merge pull request #1193 from rapidpro/polls-cyan
 * Use cyan, black and white colors for new brand on polls page
 * Merge pull request #1191 from rapidpro/dependabot/pip/jinja2-3.1.3
 * Merge pull request #1192 from rapidpro/dependabot/pip/django-4.2.10
 * Bump django from 4.2.7 to 4.2.10
 * Bump jinja2 from 3.1.2 to 3.1.3

v1.2.100 (2024-02-28)
-------------------------
 * Merge pull request #1190 from rapidpro/fix-drc-logo

v1.2.99 (2024-02-28)
-------------------------
 * Merge pull request #1189 from rapidpro/drc-logo
 * Quick workaround custom DRC logo
 * Merge pull request #1188 from rapidpro/drc-logo
 * Quick workaround custom DRC logo

v1.2.98 (2024-02-26)
-------------------------
 * Merge pull request #1187 from rapidpro/logo-lang

v1.2.96 (2024-02-08)
-------------------------
 * Fix tab title

v1.2.95 (2024-02-07)
-------------------------
 * Merge pull request #1186 from rapidpro/links-updates
 * Update VOY links

v1.2.94 (2024-02-05)
-------------------------
 * Merge pull request #1185 from rapidpro/fix-org-name-spacing
 * Fix site name spacing for global site

v1.2.93 (2024-02-05)
-------------------------
 * Merge pull request #1183 from rapidpro/fix-co-create
 * Fix logic to display co-create link

v1.2.92 (2024-01-30)
-------------------------
 * Merge pull request #1182 from rapidpro/staging-pushes
 * Hide name for global site

v1.2.91 (2024-01-29)
-------------------------
 * Fix configured colors load CSS classes

v1.2.90 (2024-01-29)
-------------------------
 * Merge pull request #1180 from rapidpro/staging-pushes
 * Show co create link for new brand only
 * Format templates
 * Adjust footer logo
 * Add Co-create link
 * Change the countries dropdown for new brand
 * Update favicon and homemap
 * Fix primary color for new brand
 * Adjust cyan button hover color
 * Fix bg color for button on mobile
 * Adjust size for UNICEF footer logo
 * Adjust the UNICEF logo in the footer
 * Adjust favicon
 * Adjust border and chart colors
 * Adjust name after logo
 * Update fonts to Noto Sans
 * Switch to use new header logo
 * Add config for switching new brand
 * Update CHANGELOG.md for v1.2.89
 * Merge pull request #1179 from rapidpro/dependabot/pip/pillow-10.2.0
 * Bump pillow from 10.1.0 to 10.2.0
 * Merge pull request #1177 from rapidpro/djlint
 * HTML templates linting

v1.2.89 (2024-01-24)
-------------------------
 * Merge pull request #1179 from rapidpro/dependabot/pip/pillow-10.2.0
 * Bump pillow from 10.1.0 to 10.2.0
 * Merge pull request #1177 from rapidpro/djlint
 * HTML templates linting

v1.2.88 (2023-11-17)
-------------------------
 * Merge pull request #1168 from rapidpro/update-ro
 * Fix romanian translations

v1.2.87 (2023-11-03)
-------------------------
 * Merge pull request #1167 from rapidpro/update-deps-1
 * Update deps

v1.2.86 (2023-10-27)
-------------------------
 * Merge pull request #1165 from rapidpro/namibia-icon
 * Add Namibia icon

v1.2.85 (2023-10-25)
-------------------------
 * Merge pull request #1166 from rapidpro/poll-published
 * Add back the sync status message for inactive polls

v1.2.83 (2023-10-18)
-------------------------
 * Merge pull request #1164 from rapidpro/update-dash
 * Update deps

v1.2.82 (2023-10-17)
-------------------------
 * Merge pull request #1163 from Ilhasoft/fix/update-translations-locale-for-en-lc
 * Fix conflict on locale/sl/LC_MESSAGES/django.po file
 * Update the django.mo file
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Removing locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl
 * Translate locale/en/LC_MESSAGES/django.po in sl

v1.2.81 (2023-10-05)
-------------------------
 * Merge pull request #1162 from rapidpro/invite-date-display
 * Run code checks
 * Add notification message for resending invites
 * Show date on invites
 * Merge pull request #1161 from rapidpro/update-deps
 * Update deps
 * Merge pull request #1160 from rapidpro/dependabot/pip/urllib3-1.26.17
 * Merge pull request #1159 from rapidpro/dependabot/npm_and_yarn/postcss-8.4.31
 * Bump urllib3 from 1.26.16 to 1.26.17
 * Bump postcss from 8.4.21 to 8.4.31

v1.2.80 (2023-09-28)
-------------------------
 * Merge pull request #1157 from Ilhasoft/add-slovenija
 * Add Slovenija Flag

v1.2.79 (2023-09-11)
-------------------------
 * Merge pull request #1148 from rapidpro/translations_locale-en-lc-messages-django-po--main_sr_RS@latin
 * Run code checks
 * Translate django.po in sr_RS@latin
 * Merge pull request #1155 from rapidpro/translations_locale-en-lc-messages-django-po--main_sl
 * Merge pull request #1156 from rapidpro/translations_locale-en-lc-messages-django-po--main_pt
 * Fix tests
 * Run code checks
 * Translate locale/en/LC_MESSAGES/django.po in pt
 * Translate locale/en/LC_MESSAGES/django.po in sl

v1.2.78 (2023-08-22)
-------------------------
 * Merge pull request #1152 from rapidpro/convert_templates
 * Update deps
 * Merge pull request #1154 from rapidpro/rowanseymour-patch-1
 * Update ci.yml

v1.2.76 (2023-07-25)
-------------------------
 * Proper variable for STORAGES

v1.2.75 (2023-07-25)
-------------------------
 * Merge pull request #1151 from rapidpro/fix-storage-settings
 * Update django storages, fix thumbnail storage setting

v1.2.74 (2023-07-06)
-------------------------
 * Merge pull request #1149 from rapidpro/update-django

v1.2.72 (2023-07-05)
-------------------------
 * Merge pull request #1147 from rapidpro/add-sudan
 * Add Sudan to countries dropdown
 * Merge pull request #1146 from rapidpro/translations_locale-en-lc-messages-django-po--main_sr_RS@latin
 * Run code_checks
 * Translate django.po in sr_RS@latin
 * Translate django.po in sr_RS@latin

v1.2.71 (2023-06-16)
-------------------------
 * Merge pull request #1098 from rapidpro/south-pacific
 * Add Somalia icon
 * Update South Pacific icon

v1.2.70 (2023-05-10)
-------------------------
 * Merge pull request #1145 from rapidpro/fix-fields
 * Run code checks
 * Remove pisa
 * Update django
 * Add transformer to client to support old fields

v1.2.69 (2023-04-20)
-------------------------
 * Fix scheme count query
 * Fix scheme count query

v1.2.68 (2023-04-20)
-------------------------
 * Merge pull request #1144 from rapidpro/fix-activity-counts
 * Fix activity counters counts queries

v1.2.67 (2023-04-20)
-------------------------
 * Merge pull request #1143 from rapidpro/fix-activity-counts
 * Fix activity counters counts queries

v1.2.66 (2023-04-20)
-------------------------
 * Merge pull request #1140 from rapidpro/contact-activities-counters-5
 * Make sure to refresh the engagement counts after recalculation
 * Switch to use contact activities counts for the graph stats

v1.2.65 (2023-04-19)
-------------------------
 * Merge pull request #1138 from rapidpro/contact-activities-counters-4
 * Merge pull request #1139 from rapidpro/contact-activities-counters-3
 * Merge pull request #1137 from rapidpro/contact-activities-counters-2
 * Merge pull request #1135 from rapidpro/contact-activities-counters
 * Add task to squash contact activities counts, manual task to recalculate the counts
 * Add methods to recalcuate the activities counts from the DB
 * fix conflicts
 * fix conflicts
 * Add and install contact activity DB triggers for counts
 * Fix squash_over org_id
 * Add Squashable abstract model, and use that on contact activity counter
 * Merge pull request #1142 from rapidpro/fix-coverage
 * Replace codecov with coverage

v1.2.64 (2023-04-19)
-------------------------
 * Merge pull request #1134 from rapidpro/more-optimizations
 * More queries optimizations
 * Merge pull request #1141 from rapidpro/update-dash
 * Update dash
 * Merge pull request #1133 from rapidpro/update-deps
 * update postcss
 * Merge pull request #1132 from rapidpro/update-deps
 * Update npm deps
 * Remove unused deps

v1.2.63 (2023-04-03)
-------------------------
 * Merge pull request #1131 from rapidpro/update-deps
 * Update deps
 * Merge pull request #1129 from rapidpro/more-optimizations
 * Merge pull request #1130 from rapidpro/dependabot/pip/redis-4.5.4
 * Bump redis from 4.5.1 to 4.5.4
 * Fix tests
 * WIP more optimizations to reduce queries with prefetch

v1.2.62 (2023-03-30)
-------------------------
 * Merge pull request #1128 from rapidpro/more-optimizations
 * Add indexes to optimize more the page loading

v1.2.61 (2023-03-29)
-------------------------
 * Fix delete old contact activities

v1.2.60 (2023-03-28)
-------------------------
 * Merge pull request #1127 from rapidpro/delete-old-contact-activities
 * Delete old contact activities task

v1.2.59 (2023-03-28)
-------------------------
 * Merge pull request #1126 from rapidpro/line-button
 * Run code checks
 * Fix conflicts
 * Add line link on join page
 * Merge pull request #1125 from rapidpro/translations_locale-en-lc-messages-django-po--main_th
 * Run code checks
 * Translate locale/en/LC_MESSAGES/django.po in th

v1.2.58 (2023-03-16)
-------------------------
 * Add Thai

v1.2.57 (2023-03-16)
-------------------------
 * Merge pull request #1111 from rapidpro/translations_locale-en-lc-messages-django-po--main_th
 * Run code_checks
 * Translate locale/en/LC_MESSAGES/django.po in th
 * Merge pull request #1107 from rapidpro/translations_locale-en-lc-messages-django-po--main_th
 * Run code_checks
 * Translate locale/en/LC_MESSAGES/django.po in th
 * Merge pull request #1089 from rapidpro/translations_locale-en-lc-messages-django-po--main_fr
 * Merge pull request #1090 from rapidpro/translations_locale-en-lc-messages-django-po--main_el
 * Merge pull request #1092 from rapidpro/translations_locale-en-lc-messages-django-po--main_cs
 * Run code_checks
 * Translate locale/en/LC_MESSAGES/django.po in fr
 * Run code_checks
 * Translate locale/en/LC_MESSAGES/django.po in el
 * Run code_checks
 * Translate locale/en/LC_MESSAGES/django.po in cs
 * Merge pull request #1097 from rapidpro/update-haml
 * Update hamply
 * enable makemessages to generate PO files
 * Run black
 * Remove flake8, Add ruff

v1.2.56 (2023-03-02)
-------------------------
 * Merge pull request #1096 from rapidpro/fix-translations
 * Add caching to the shared sites count view
 * Disable update PO files
 * Revert to correct locale PO files
 * Merge pull request #1095 from rapidpro/update-GA-actions
 * Remove testing on old versions

v1.2.55 (2023-02-27)
-------------------------
 * Merge pull request #1094 from rapidpro/fix-story-errors
 * Fix stories validation and have the errors well noticeable

v1.2.54 (2023-02-22)
-------------------------
 * Update dash and poetry lock file
 * Use latest deps updates
 * Update Thailand icons

v1.2.51
----------
 * Merge pull request #1084 from rapidpro/micronesia
 * Add micronesia
 * Merge pull request #1083 from rapidpro/test-pg-14
 * Test on redis 6.2
 * Merge pull request #1082 from rapidpro/test-pg-14
 * Test on PG 14

v1.2.50
----------
 * Merge pull request #1081 from rapidpro/update-cg-logo
 * Update CG logo
 * Merge pull request #1079 from rapidpro/update-test-db
 * Update deps
 * Start testing PG 13

v1.2.49
----------
 * Merge pull request #1076 from rapidpro/poll-preview
 * Run code checks
 * Add preview button on poll admin list
 * Run code_checks
 * Add poll preview view for admin to see stats for unpublished polls
 * Move black setting into pyproject.toml

v1.2.48
----------
 * Merge pull request #1077 from rapidpro/add-mauritania
 * Run code checks
 * Add Mauritania flag
 * Merge pull request #1075 from Ilhasoft/uk-language
 * update locale mo file for uk language
 * Translate /locale/en/LC_MESSAGES/django.po in uk

v1.2.47
----------
 * Merge pull request #1073 from rapidpro/add-morocco
 * Merge pull request #1072 from Ilhasoft/feature/europe.flag
 * rename flag and countries code
 * Adding favico europe
 * Add Morocco flag
 * fix identation
 * Adding Europe's Flag

v1.2.46
----------
 * Merge pull request #1071 from rapidpro/dependabot/pip/django-4.0.4
 * Merge pull request #1070 from rapidpro/dependabot/npm_and_yarn/minimist-1.2.6
 * Bump django from 4.0.3 to 4.0.4
 * Bump minimist from 1.2.5 to 1.2.6
 * Run code checks

v1.2.45
----------
 * Merge pull request #1069 from rapidpro/fix-lock-time
 * Adjust lock timeout for rebuilding poll results

v1.2.44
----------
 * Merge pull request #1067 from rapidpro/fix-rebuild-counts-task
 * Run code checks
 * Add lock when  task rebuilding counts is running

v1.2.43
----------
 * Merge pull request #1066 from rapidpro/fix-week-number-bug
 * Avoid using date that will match same week as the current week in the past year

v1.2.42
----------
 * Merge pull request #1065 from pauloabreu/fix/unicef-logo
 * fix unicef logo
 * Merge pull request #1064 from Ilhasoft/locale-el-adjusts
 * update locale for el language
 * Translate /locale/en/LC_MESSAGES/django.po in el

v1.2.41
----------
 * Merge pull request #986 from rapidpro/optimization-debug
 * Update deps
 * fix conflicts
 * Update deps
 * Remove unused dashblock types loading
 * Reduce queries
 * Update and activate django debug toolbar

v1.2.40
----------
 * Merge pull request #1031 from Ilhasoft/update-el-language
 * Merge pull request #1030 from rapidpro/inc_paths
 * update .mo file for el language
 * Pass paths=true to runs API endpoint
 * Translate /locale/en/LC_MESSAGES/django.po in el
 * Merge pull request #985 from Ilhasoft/feature/greece.flag
 * Adding Greece's Flag

v1.2.39
----------
 * Merge pull request #952 from rapidpro/optimize-home
 * More optimization and update tests

v1.2.38
----------
 * Merge pull request #951 from rapidpro/cache-no-expire
 * Do not expire the cached counts

v1.2.37
----------
 * Merge pull request #950 from rapidpro/fix-pills
 * Merge pull request #949 from Ilhasoft/locale/greek
 * Fix pills borders
 * adding .mo file for el language
 * enable greek language (el) on settings
 * fix bugs on el locale
 * Translate /locale/en/LC_MESSAGES/django.po in el

v1.2.36
----------
 * Merge pull request #947 from Ilhasoft/fix/change-name-Nic-countries_codes
 * add s in countries_codes Nicaragua

v1.2.35
----------
 * Merge pull request #946 from rapidpro/org-contacts-count-cache
 * do not expire the org contact counts cache

v1.2.34
----------
 * Merge pull request #945 from rapidpro/hide-menu-for-anon
 * Hide left menu of forget password page

v1.2.33
----------
 * Merge pull request #941 from rapidpro/sec-updates

v1.2.31
----------
 * Merge pull request #940 from rapidpro/translations_locale-en-lc-messages-django-po--main_fr
 * Merge pull request #942 from rapidpro/update-deps
 * Run code checks
 * Update deps
 * Translate /locale/en/LC_MESSAGES/django.po in fr
 * Merge pull request #897 from rapidpro/sec-updates

v1.2.30
----------
 * Merge pull request #895 from rapidpro/percent-graphs
 * Fix polls graphs percentage bar lengths

v1.2.29
----------
 * Merge pull request #859 from rapidpro/update-deps

v1.2.26
----------
 * Update deps
 * Merge pull request #857 from rapidpro/translations_locale-en-lc-messages-django-po--main_fr
 * Merge pull request #858 from rapidpro/django4
 * Add migrations
 * Run code checks
 * Merge branch 'main' of github.com:rapidpro/ureport into HEAD
 * Merge pull request #856 from rapidpro/django4
 * Translate /locale/en/LC_MESSAGES/django.po in fr
 * Update pillow to 9.0.0
 * Update to support django 4
 * Run code_checks
 * Prep update for django 4.0

v1.2.25
----------
 * Merge pull request #851 from alviriseup/main
 * Changes commited
 * Removed whitespaces and unused variables
 * Merge branch 'main' of https://github.com/alviriseup/ureport into main
 * Added Tests, Fixed inverted logic
 * Delete views_20220103190914.py
 * Delete views_20220103184452.py
 * Delete serializers_20220103185012.py
 * Delete serializers_20220103184452.py
 * example for field and exclude API call
 * Added functions for fields and exclude API call

v1.2.24
----------
 * Merge pull request #853 from rapidpro/gender-label-stats-fix
 * Fix issue for gender stats

v1.2.23
----------
 * Run code checks
 * Merge pull request #852 from rapidpro/absolute_count
 * Merge pull request #846 from rapidpro/translations_locale-en-lc-messages-django-po--main_cs
 * Add Niger logo
 * Add absolute count of age stats and schemes stats for API only
 * Translate /locale/en/LC_MESSAGES/django.po in cs

v1.2.22
----------
 * Remove Niger logo
 * Merge pull request #848 from Ilhasoft/feature/nicaragua-flag
 * Add Favico Flag Nicaragua
 * Merge branch 'main' of https://github.com/rapidpro/ureport into feature/nicaragua-flag
 * Adding Nicaragua's Flag - update 2
 * Adding Nicaragua's Flag

v1.2.21
----------
 * Merge pull request #845 from rapidpro/add-niger
 * Add Niger flag

v1.2.20
----------
 * Merge pull request #843 from rapidpro/revert-poll-stats-insert-on-sync
 * Revert to always recalculate poll stats

v1.2.19
----------
 * Merge pull request #841 from rapidpro/gender-stats-fix
 * Make sure the org language is activate for gender stats
 * Merge pull request #840 from rapidpro/word-cloud-fix
 * Populate flow result on word clouds objects
 * Merge pull request #839 from rapidpro/install_poetry
 * Install poetry the proper way during CI

v1.2.18
----------
 * Merge pull request #837 from rapidpro/rebuild-polls-counts
 * Rebuild stats once a day

v1.2.17
----------
 * Merge pull request #836 from rapidpro/squash-stats-dedupe
 * Make sure only one task is squashing the stats at a time

v1.2.16
----------
 * Merge pull request #834 from rapidpro/optimize-sync-stats-creations

v1.2.15
----------
 * Merge pull request #833 from rapidpro/syncing-improvements
 * Run code checks
 * Remove brick polls tasks, only clear results for poll not stopped syncing

v1.2.14
----------
 * Merge pull request #832 from rapidpro/remove-unused-context-variables
 * Remove border on partner logos
 * Remove unused context variables

v1.2.13
----------
 * Merge pull request #831 from rapidpro/remove-photos
 * Run code checks
 * Remove photos section

v1.2.12
----------
 * Merge pull request #830 from rapidpro/about-partners
 * fix conflicts
 * Merge pull request #829 from rapidpro/question-hidden-charts-config
 * Merge pull request #816 from rapidpro/landing_pages_bots

v1.2.11
----------
 * Merge pull request #828 from rapidpro/fix-dashblock-views
 * Update deps

v1.2.10
----------
 * Fix flags name

v1.2.9
----------
 * Merge pull request #813 from rapidpro/story-attachment-reports
 * fix conflicts, merge main
 * Merge pull request #827 from rapidpro/unicef-footer-logo
 * Update black
 * Update code checks
 * Add option to allow admin to hide/show the UNICEF logo in the footer
 * Run code checks
 * Update rapidpro-dash
 * Merge pull request #825 from rapidpro/poll-top-section-share
 * Merge pull request #824 from rapidpro/unicef-footer-logo
 * Merge pull request #819 from rapidpro/favicos
 * Update rapidpro-dash
 * Use the black UNICEF logo
 * Adjust responsiveness
 * Support localized UNICEF logos
 * UNICEF logo in footer center
 * Add sharing buttons on the top of the poll summary section
 * Display favicos for sites by subdomain
 * Update favicos
 * Rename flag files to match the subdomain used for each site
 * Cleaner favicons
 * Add favicon for sudan
 * Add Sudan flag
 * Add gabon favicon
 * Add flag favico assets
 * Adjust title of story page
 * Fix attachment URL
 * Add border for reports page list
 * Fix reports order
 * Fix attachment URL
 * Run code checks
 * Add reports public pages
 * update deps
 * Fix conflicts
 * Run code checks
 * Run code checks
 * Filter stories to keep current behaviour excluding rows with PDF attachments

v1.2.8
----------
 * Merge pull request #822 from rapidpro/more-stats-indexes
 * Add more stats indexes

v1.2.7
----------
 * Merge pull request #821 from rapidpro/fix-indexes
 * Rebuild the index properly

v1.2.6
----------
 * Merge pull request #818 from rapidpro/better-indexes-2
 * Remove unused indexes

v1.2.5
----------
 * Merge pull request #817 from rapidpro/better-indexes
 * Rebuild indexes properly

v1.2.4
----------
 * Fix variable referenced before assignment

v1.2.3
----------
 * Run code checks
 * Merge pull request #807 from rapidpro/task-update-old-contact-activities
 * Merge pull request #806 from rapidpro/contact-activity-better-smaller-indexes
 * Fix typo
 * Add better smaller index and use used field in the queries
 * Add task to update old contact activities to have used field False

v1.2.2
----------
 * Merge pull request #812 from rapidpro/fix-html-unescape

v1.2.1
----------
 * Fix prod settings for celery

v1.2.0
----------
 * Merge pull request #810 from rapidpro/update-deps-dash-1.8.1

v1.1.305
----------
 * Merge pull request #809 from rapidpro/add-gabon
 * Add Gabon flag

v1.1.304
----------
 * Merge pull request #808 from rapidpro/disable_sentry_transactions
 * Disable sentry transaction collecting

v1.1.303
----------
 * Merge pull request #805 from rapidpro/contact-activities-optimizations-part2
 * Populate the used field for contact activities with a date in the last 13 months

v1.1.302
----------
 * Merge pull request #799 from rapidpro/contact-activities-optimizations

v1.1.301
----------
 * Merge pull request #801 from rapidpro/fix-age-chart-labels
 * Merge pull request #803 from rapidpro/poll-search-feedback

v1.1.300
----------
 * Fix bots padding

v1.1.299
----------
 * Merge pull request #798 from rapidpro/bot-listing
 * Fix the ordering of links
 * Merge pull request #794 from rapidpro/question-colors-choice
 * Fix mobile link for bots
 * Run code_checks
 * Fix conflicts
 * Merge pull request #789 from rapidpro/bot-listing
 * Update CHANGELOG.md for v1.1.298
 * Merge pull request #795 from rapidpro/more-indexes
 * Update CHANGELOG.md for v1.1.297
 * Merge pull request #793 from rapidpro/few-queries-for-rebuild-stats
 * Merge pull request #796 from Ilhasoft/feature/translations_django-po--master_ru
 * translation completed for the source file '/locale/en/LC_MESSAGES/django.po' on the 'ru' language.
 * Remove count of poll results IDs in rebuilt poll stats
 * Add more index on contact activities

v1.1.298
----------
 * Merge pull request #795 from rapidpro/more-indexes
 * Add more index on contact activities

v1.1.297
----------
 * Merge pull request #793 from rapidpro/few-queries-for-rebuild-stats
 * Merge pull request #796 from Ilhasoft/feature/translations_django-po--master_ru
 * translation completed for the source file '/locale/en/LC_MESSAGES/django.po' on the 'ru' language.
 * Remove count of poll results IDs in rebuilt poll stats

v1.1.296
----------
 * Merge pull request #781 from rapidpro/engagement-chart-2
 * Fix conflicts
 * Merge pull request #790 from rapidpro/dependabot/npm_and_yarn/nth-check-2.0.1
 * Merge pull request #785 from rapidpro/join-c2a
 * Fix conflicts
 * Merge pull request #786 from rapidpro/remove-v1-colors-use
 * Test on Python 3.9
 * Bump nth-check from 2.0.0 to 2.0.1
 * Merge main
 * Run code_checks
 * Add join call to action text config
 * Adjust colors for join call to action button on the top
 * Make sure to fill the colors list with the default colors
 * Merge branch 'main' of github.com:rapidpro/ureport into remove-v1-colors-use
 * Run code_checks
 * Merge branch 'main' of github.com:rapidpro/ureport into engagement-chart-2
 * Merge pull request #787 from rapidpro/fix-reverse-migrations
 * Merge branch 'main' of github.com:rapidpro/ureport into engagement-chart-2

v1.1.295
----------
 * Merge pull request #784 from rapidpro/FB-customerchat-dialog-hidden
 * Merge pull request #783 from rapidpro/resumable-scheme-backfill
 * Merge pull request #782 from rapidpro/better-index
 * Merge pull request #779 from rapidpro/engagement-chart-1
 * Hide customer chat plugin dialog until user clicks on it
 * Run code_check
 * Make scheme backfill tasks resumable
 * Show chart breakdown by default on engagement page
 * Add better indexes
 * Merge pull request #780 from Ilhasoft/feature/kyrgyzstan-flag
 * feat: Add Kyrgyzstan flag

v1.1.294
----------
 * Merge pull request #778 from rapidpro/use-slow-queue-to-backfill
 * Use the slow queue to backfill the schemes

v1.1.293
----------
 * Merge pull request #777 from rapidpro/make_many_different_task_to_backfill
 * Distribute the backfill task for schemes

v1.1.292
----------
 * Merge pull request #775 from rapidpro/support-scheme-2
 * Fix returned tuple assignment for get_or_create
 * Copy actually task code to not go through the decorator
 * For pull contacts from scratch if we have contacts without scheme set
 * Fix query
 * Fix argument to pull_contact method
 * Add task to populate the schemes
 * Save scheme on contact activity
 * Save scheme on poll stats
 * Add sign rate by scheme function
 * Run code checks
 * Write scheme for contacts and poll results when syncing

v1.1.291
----------
 * Merge pull request #776 from rapidpro/add-benin
 * Add Benin icon
 * Merge pull request #774 from rapidpro/support-scheme-1
 * WIP add Benin to countries list

v1.1.289
----------
 * Merge pull request #773 from rapidpro/dashblock-api

v1.1.286
----------
 * Merge pull request #771 from rapidpro/poll-cloud-query
 * Adjust poll word cloud query

v1.1.285
----------
 * Merge pull request #770 from rapidpro/fix-engagements-queries
 * Update engagment stats to start using flow result foreign key

v1.1.284
----------
 * Merge pull request #769 from rapidpro/fix-responded
 * Fix query for responded counts

v1.1.283
----------
 * Merge pull request #753 from rapidpro/flow-results-6
 * Merge pull request #768 from Ilhasoft/feature/sverige_flag
 * feature: sverige flag
 * Merge branch 'main' of github.com:rapidpro/ureport into flow-results-6
 * Build a unique set of stats going forward, for existing stats check if we need to filter by question

v1.1.282
----------
 * Merge pull request #767 from rapidpro/fix-localization
 * Adjust styles
 * Make text localizable

v1.1.281
----------
 * Merge pull request #766 from rapidpro/add-tags
 * Merge pull request #765 from rapidpro/dependabot/npm_and_yarn/path-parse-1.0.7
 * Remove is_active tag check
 * Bump path-parse from 1.0.6 to 1.0.7

v1.1.277
----------
 * Add MO file
 * Merge pull request #764 from rapidpro/contact-counts-monitor
 * Merge pull request #763 from rapidpro/update-README
 * Add message for when the contact task is running on status for mismatch counts
 * Update README
 * Merge pull request #761 from rapidpro/translations_django-po--master_sv_SE
 * Apply translations in sv_SE

v1.1.276
----------
 * Merge pull request #756 from rapidpro/update-contacts-triggers
 * Merge branch 'main' of github.com:rapidpro/ureport into update-contacts-triggers
 * Merge branch 'main' of github.com:rapidpro/ureport into update-contacts-triggers
 * Run code_checks
 * Grab lock when recalculating the contacts stats
 * Fix bugs in contacts triggers

v1.1.275
----------
 * Merge pull request #760 from rapidpro/counts-status
 * Show calculated stats too on counts status

v1.1.274
----------
 * Merge pull request #759 from rapidpro/counts-status
 * Better stats on counts status

v1.1.273
----------
 * Merge pull request #758 from rapidpro/counts-status
 * consider mismatch for a diff more that 50 or 2.5%

v1.1.272
----------
 * Merge pull request #757 from rapidpro/counts-status
 * Add counts status view

v1.1.271
----------
 * Merge pull request #755 from rapidpro/update-result-for-new-contacts
 * Merge branch 'main' of github.com:rapidpro/ureport into update-result-for-new-contacts
 * Run code_checks
 * Update results for new contacts

v1.1.270
----------
 * Merge pull request #754 from rapidpro/django-3

v1.1.269
----------
 * Merge pull request #752 from evansmurithi/add-madagasikara-flag
 * Add Madagascar flag

v1.1.268
----------
 * Merge pull request #746 from rapidpro/flow-results-5
 * Populate flow result on poll stats

v1.1.267
----------
 * Merge pull request #745 from rapidpro/flow-results-4
 * Merge branch 'main' of github.com:rapidpro/ureport into flow-results-4
 * Update CHANGELOG.md for v1.1.265
 * Merge pull request #751 from rapidpro/dedupe-poll-response-categories
 * Merge pull request #750 from rapidpro/unique-pollresponsecategory-constraint
 * Update CHANGELOG.md for v1.1.264
 * Fix migration queryset
 * Fix migration queryset
 * Update CHANGELOG.md for v1.1.263
 * Merge pull request #749 from rapidpro/dedupe-poll-response-categories
 * Add constraint for unique together on poll response categories
 * Fix field name
 * Improve the way to select the obj to keep
 * Add migrations to deduplicates the poll response categories
 * Update CHANGELOG.md for v1.1.260
 * Merge pull request #748 from rapidpro/fix-constraint
 * Remove constraints on PollResponseCategory
 * Update CHANGELOG.md for v1.1.258
 * Merge pull request #747 from rapidpro/flow-results-2
 * Merge pull request #744 from rapidpro/flow-results-3
 * Update CHANGELOG.md for v1.1.257
 * Merge pull request #741 from rapidpro/flow-results-2
 * Update CHANGELOG.md for v1.1.256
 * Merge pull request #743 from rapidpro/tests-methods
 * Merge master
 * Merge pull request #742 from rapidpro/remove-poll-import
 * Merge pull request #740 from rapidpro/separate-data-models-and-display-config-models
 * Add test methods to create questions and response categories
 * Remove unused polls import

v1.1.265
----------
 * Merge pull request #751 from rapidpro/dedupe-poll-response-categories
 * Merge pull request #750 from rapidpro/unique-pollresponsecategory-constraint
 * Add constraint for unique together on poll response categories

v1.1.264
----------
 * Fix migration queryset
 * Fix migration queryset

v1.1.263
----------
 * Merge pull request #749 from rapidpro/dedupe-poll-response-categories

v1.1.260
----------
 * Merge pull request #748 from rapidpro/fix-constraint

v1.1.258
----------
 * Merge pull request #747 from rapidpro/flow-results-2
 * Merge pull request #744 from rapidpro/flow-results-3
 * fix conflicts
 * Use fields from flow results and flow result categories

v1.1.257
----------
 * Merge pull request #741 from rapidpro/flow-results-2
 * Migrate poll question that do not have the flow result field yet set
 * Add data migrations to populate the flow results and flow result categories

v1.1.256
----------
 * Merge pull request #743 from rapidpro/tests-methods
 * Merge master
 * Merge pull request #742 from rapidpro/remove-poll-import
 * Merge pull request #740 from rapidpro/separate-data-models-and-display-config-models
 * Simpler querysets
 * Add test methods to create questions and response categories
 * Remove unused polls import

v1.1.254
----------
 * Merge pull request #736 from rapidpro/sync-reverse
 * Change last pull results redis key so polls still syncing do not miss results
 * Update CHANGELOG.md for v1.1.252
 * Merge pull request #739 from rapidpro/fix-boundaries-ids
 * Fix boundaries to allow IDs with dots
 * Update CHANGELOG.md for v1.1.251
 * Merge pull request #643 from Ilhasoft/feature/add-uniendovoces-flags
 * add country codes to uniendo voces workspaces
 * Merge branch 'main' of https://github.com/rapidpro/ureport into feature/add-uniendovoces-flags
 * fix uniendo voces ecuador sintaxe
 * add uniendo voces flags

v1.1.252
----------
 * Merge pull request #739 from rapidpro/fix-boundaries-ids
 * Fix boundaries to allow IDs with dots

v1.1.251
----------
 * Merge pull request #643 from Ilhasoft/feature/add-uniendovoces-flags
 * add country codes to uniendo voces workspaces
 * Merge branch 'main' of https://github.com/rapidpro/ureport into feature/add-uniendovoces-flags
 * fix uniendo voces ecuador sintaxe
 * add uniendo voces flags

v1.1.250
----------
 * Merge pull request #728 from Ilhasoft/feature/eastern-caribbean-flag
 * Merge pull request #644 from Ilhasoft/feature/add-oecs-flag
 * fix: Adjusted Eastern Caribbean flag
 * fix: Runing black
 * fix: Adjusted OECS flag and countries_codes
 * add eastern caribbean flag on ureport
 * fix: Fix countries code OECS remove the flag
 * fix the name of flag file
 * add oecs flag

v1.1.249
----------
 * Merge pull request #735 from rapidpro/responders
 * Compile messages
 * Update translations
 * Merge pull request #734 from rapidpro/responders
 * Rename responses to responders

v1.1.248
----------
 * Merge pull request #733 from rapidpro/contact-pull-on-status
 * Better ordering or keys

v1.1.247
----------
 * Merge pull request #732 from rapidpro/contact-pull-on-status
 * Add tasks last successful time on task status endpoint

v1.1.246
----------
 * Merge pull request #731 from rapidpro/contact-pull-on-status
 * Add a new task status endpoint

v1.1.245
----------
 * Merge pull request #730 from rapidpro/icons
 * Add view to display icons added are matching the dimensions expected
 * Merge pull request #729 from rapidpro/contact-pull-on-status
 * Add contact sync up key to status monitoring endpoint

v1.1.244
----------
 * Merge pull request #727 from rapidpro/fix-reported-errors
 * Fix API endpoint to only accept int IDs

v1.1.243
----------
 * Merge pull request #726 from rapidpro/increase-engagement-data-lock-time
 * Increase lock timeout for refreshing engagement data task

v1.1.242
----------
 * Merge pull request #725 from rapidpro/update-js-deps

v1.1.240
----------
 * Merge pull request #723 from rapidpro/add-index-org-question
 * Add index on poll stats org and question

v1.1.239
----------
 * Merge pull request #722 from Ilhasoft/feature/paraguay-flag
 * Merge pull request #721 from rapidpro/dependabot/npm_and_yarn/lodash-4.17.21
 * Add Paraguay flag
 * Bump lodash from 4.17.19 to 4.17.21

v1.1.238
----------
 * Merge pull request #719 from rapidpro/fix-join-icons
 * fix join icons to use a grid of 3 cols
 * Merge pull request #718 from Ilhasoft/hotfix/change-kenya-address
 * fix to change address from Kenya Ureport

v1.1.237
----------
 * Merge pull request #716 from rapidpro/add-Angola
 * Merge pull request #717 from rapidpro/add-telegram-bot-config
 * Add Telegram bot org config
 * Add Angola icon

v1.1.236
----------
 * Merge pull request #715 from Ilhasoft/feature/italia-flag
 * fix: Update Italy map
 * Merge pull request #714 from Ilhasoft/feature/kenya-flag
 * feat: Add Italia flag
 * feat: Add Kenya flag

v1.1.235
----------
 * Merge pull request #712 from Ilhasoft/feature/stp-flag
 * fix: Removed ST from countries_codes
 * feat: Added São Tomé and Príncipe flag

v1.1.234
----------
 * Merge pull request #713 from rapidpro/GTM
 * Add support for Google Tag Manager

v1.1.233
----------
 * Merge pull request #711 from rapidpro/fix-errors
 * Fix errors breaking the clear old results

v1.1.232
----------
 * Merge pull request #710 from rapidpro/add-exc-info-to-error
 * add execution info on error logging

v1.1.231
----------
 * Merge pull request #709 from rapidpro/FB-verification
 * Add configuration for FB domain verification

v1.1.230
----------
 * Merge pull request #708 from rapidpro/fix-top-question-lookup
 * Skip rebuilding stats for inactive polls

v1.1.229
----------
 * Merge pull request #707 from rapidpro/fix-top-question-lookup
 * Fix top question lookup

v1.1.228
----------
 * Merge pull request #706 from rapidpro/update-district-caches
 * Run code checks
 * Update district poll results cache

v1.1.227
----------
 * Merge pull request #705 from rapidpro/adjust-sync-schedule-message
 * Adjust message for sync schedule

v1.1.226
----------
 * Merge pull request #701 from rapidpro/translations_django-po--master_hr_HR
 * Merge pull request #704 from rapidpro/keep-results-longer
 * Run code checks
 * Merge branch 'translations_django-po--master_hr_HR' of github.com:rapidpro/ureport into translations_django-po--master_hr_HR
 * Merge pull request #703 from rapidpro/better-indexes
 * Keep poll results for up to a year syncing from RapidPro
 * Run code checks
 * Add partial indexes
 * Apply translations in hr_HR

v1.1.225
----------
 * Merge pull request #702 from rapidpro/fix-colors-poll-status-message
 * Fix primary  color, adjust poll status message

v1.1.224
----------
 * Merge pull request #699 from rapidpro/fix-clear-results
 * Log error for clearing results, and continue for other polls

v1.1.223
----------
 * Merge pull request #698 from rapidpro/fix-boundaries-url
 * Run code checks
 * Add support for hyphens and underscore in osm IDs for boundaries URLs

v1.1.222
----------
 * Merge pull request #697 from rapidpro/fix-date-format
 * Fix to handle flow date as a json datetime

v1.1.221
----------
 * Merge pull request #696 from rapidpro/adding-poll-from-flow-archived-results
 * More tests
 * Update django
 * Pull results from archives for really old flow polls

v1.1.220
----------
 * Merge pull request #691 from rapidpro/update-dash
 * Merge pull request #694 from rapidpro/fix-search
 * Fix search toggle button
 * Merge pull request #693 from rapidpro/fix-sec-alerts
 * Merge pull request #692 from rapidpro/translations_django-po--master_sr_RS@latin
 * Fix sec alerts
 * Rn code checks
 * Update test deps
 * Apply translations in sr_RS@latin
 * Update to use latest rapidpro-dash

v1.1.219
----------
 * Merge pull request #690 from rapidpro/poll-sync-modified-on
 * Update Poll modified_on when the new poll results are completed
 * Merge pull request #689 from rapidpro/update-deps
 * Remove unused file
 * Update deps
 * Merge pull request #687 from Ilhasoft/feat/add-macedonia-flag
 * Merge pull request #686 from rapidpro/translations_django-po--master_mk_MK
 * Merge pull request #688 from rapidpro/dependabot/npm_and_yarn/y18n-4.0.1
 * Bump y18n from 4.0.0 to 4.0.1
 * Add macedonia flag
 * Apply translations in mk_MK
 * Merge pull request #685 from rapidpro/translations_django-po--master_mk_MK
 * Run code checks
 * Apply translations in mk_MK

v1.1.218
----------
 * Bump elliptic from 6.5.3 to 6.5.4
 * Add Solomon Islands flag

v1.1.217
----------
 * Merge pull request #666 from rapidpro/panama-flag
 * Update README.md
 * Merge pull request #681 from Ilhasoft/feature/macedonia-language
 * feat: Added Macedonian language
 * Add Panama icon

v1.1.216
----------
 * Revert Add Macedonia's flag


v1.1.215
----------
 * Fix Canada URL

v1.1.214
----------
 * Fix changelog
 * Revert Update AWS DEFAULT ACL
 * Update AWS DEFAULT ACL
 * Revert Add a public storage class to use with thumbnail


v1.1.213
----------
 * Merge pull request #679 from rapidpro/fix-thumbnail-storage0-permission
 * Merge pull request #678 from Ilhasoft/feature/add-macedonia-flag
 * Add a public storage class to use with thumbnail
 * Add flag file and inset into settings_common dict

v1.1.212
----------
 * Merge pull request #677 from rapidpro/polls-api-order
 * Add optional parameters to sort polls by modified on descending when that is specified
 * Merge pull request #676 from rapidpro/use-poetry

v1.1.210
----------
 * Merge pull request #675 from rapidpro/better-display-of-login-errors
 * Better display login errors

v1.1.209
----------
 * Merge pull request #673 from rapidpro/update-smartmin
 * Merge pull request #672 from rapidpro/fix-sec-issues
 * Update deps
 * Update jquery
 * Make more variables safer with strip_tags

v1.1.208
----------
 * Add locale
 * Merge pull request #671 from rapidpro/custom-join-button
 * Run code checks
 * Allow customizing join button text

v1.1.207
----------
 * Fix count link

v1.1.206
----------
 * Merge pull request #669 from rapidpro/translations_django-po--master_mk_MK
 * Merge pull request #670 from rapidpro/update-sentry-sdk
 * Update sentry SDK
 * Apply translations in mk_MK

v1.1.205
----------
 * Merge pull request #667 from rapidpro/update-idx
 * Move FB pixel to public site
 * Add index on reporterscounter
 * Bump CI testing to PG 11 and 12

v1.1.204
----------
 * Merge pull request #664 from rapidpro/polls-api
 * Merge pull request #665 from rapidpro/countries-flag
 * Run code checks
 * Add Canada on countries list
 * Filter API polls to only show polls displayed on the public site
 * Merge pull request #662 from rapidpro/dependabot/npm_and_yarn/ini-1.3.8
 * Bump ini from 1.3.5 to 1.3.8

v1.1.203
----------
 * Merge pull request #659 from rapidpro/fix-chart-labels-alignment
 * Align labels to the left

v1.1.202
----------
 * Merge pull request #658 from rapidpro/fix-stories-homepage

v1.1.200
----------
 * Merge pull request #657 from rapidpro/sec-adjustments

v1.1.197
----------
 * Merge pull request #656 from rapidpro/fix-counts-cache-to-consider
 * Generate cache keys for the configured sites only

v1.1.196
----------
 * Merge pull request #655 from rapidpro/pacific-as-1
 * Regional site countries excluded from count for now

v1.1.195
----------
 * Merge pull request #654 from rapidpro/add-np
 * Add Nepal to countries dropdown
 * Run code check
 * Merge pull request #653 from rapidpro/translations_django-po--master_no
 * Translate /locale/en/LC_MESSAGES/django.po in no

v1.1.194
----------
 * Merge pull request #646 from rapidpro/fix-countries-count
 * Update pacific countries

v1.1.193
----------
 * Merge pull request #645 from rapidpro/fix-countries-count
 * Remove unused flags
 * Use ISO codes of countries to count site countries

v1.1.192
----------
 * Merge pull request #642 from rapidpro/shared-flags
 * Add view for shared sites count

v1.1.191
----------
 * Merge pull request #641 from rapidpro/fix-duplicated-country-name
 * Fix counries duplicate name

v1.1.190
----------
 * Merge pull request #640 from rapidpro/add-AFG
 * Update tests
 * Add Afghanistan link

v1.1.189
----------
 * Update API docs

v1.1.188
----------
 * Update npm packages
 * Merge pull request #639 from rapidpro/updates

v1.1.183
----------
 * Merge pull request #635 from rapidpro/remove-zambia-link
 * Run code check
 * Remove broken Zambia link
 * Merge pull request #628 from rapidpro/translations_django-po--master_no
 * Merge pull request #632 from rapidpro/translations_django-po--master_sr_RS@latin
 * Merge pull request #634 from Ilhasoft/translations_django-po--master_sr_RS@latin
 * Merge pull request #633 from Ilhasoft/translations_django-po--master_no
 * run code_check
 * run code_check
 * Apply translations in sr_RS@latin
 * Translate /locale/en/LC_MESSAGES/django.po in no

v1.1.182
----------
 * Merge pull request #630 from rapidpro/fix-polls-page-slow
 * Run code check
 * Cache question responded count and polled count

v1.1.181
----------
 * Merge pull request #629 from rapidpro/fix-polls-page-slow
 * Fix opinions page to load faster

v1.1.180
----------
 * Merge pull request #626 from rapidpro/get-public-poll-query
 * Run code check
 * Never expire cache for poll results and rebuild them once a day
 * Try to use category index for getting polls

v1.1.179
----------
 * Log cache misses
 * Merge pull request #578 from Ilhasoft/feature/viber
 * Merge pull request #624 from Ilhasoft/feature/enable-no-language
 * fix tests
 * Merge remote-tracking branch 'origin/master' into feature/viber
 * run code check
 * Enable Norwegian language
 * Merge branch 'master' into feature/viber
 * Merge branch 'master' of https://github.com/rapidpro/ureport into feature/viber
 * removed old font-aweasome version
 * Change url
 * Change viber_url to viber_username
 * Fix flake8
 * Fix flake8
 * Fix flake8
 * Fix messages
 * Fix flake8
 * Fix messages
 * Fix messages
 * Fix messages
 * Fix flake8
 * Fix messages
 * Update messages
 * Update messages
 * Merge branch 'feature/viber' of https://github.com/Ilhasoft/ureport into HEAD
 * Update messages
 * Fix tests
 * Merge branch 'feature/viber' of https://github.com/Ilhasoft/ureport into HEAD
 * Fix tests
 * Merge branch 'feature/viber' of https://github.com/Ilhasoft/ureport into feature/viber
 * Fix tests
 * Update messages
 * Update settings_commons
 * Added support for viber
 * Added support for viber

v1.1.178
----------
 * Run code check
 * Merge pull request #622 from Ilhasoft/fix/temba_client-migrate-version
 * Merge pull request #582 from Ilhasoft/feature/font-aweasome-5
 * Merge pull request #623 from rapidpro/translations_django-po--master_no
 * removed viber icon from font-aweasome update branch
 * Translate /locale/en/LC_MESSAGES/django.po in no
 * fixed prefix
 * Merge pull request #621 from Ilhasoft/feature/add-norge-flag
 * Merge branch 'master' of https://github.com/rapidpro/ureport into feature/font-aweasome-5
 * applied fix from sugestion
 * fixed temba_client version to v2
 * fix pep8
 * change the flag name
 * add norge flag
 * Merge pull request #619 from rapidpro/translations_django-po--master_hr_HR
 * Run code check
 * Merge branch 'master' into translations_django-po--master_hr_HR
 * Apply translations in hr_HR
 * Fix icons
 * Updated icons for font aweasome 5

v1.1.177
----------
 * Merge pull request #620 from rapidpro/update-cache-for-polls-no-longer-syncing
 * Update cache for results for poll stopped syncing, reduce number we call slow queries
 * Merge pull request #618 from Ilhasoft/feature/add-croatian-flag
 * fix the white space
 * add Croatia flag

v1.1.176
----------
 * Increase session age

v1.1.175
----------
 * Adjust SECURE HSTS SECONDS

v1.1.174
----------
 * Merge pull request #617 from rapidpro/adjust-hsts-time
 * Adjust SECURE HSTS SECONDS

v1.1.173
----------
 * Fix typo

v1.1.172
----------
 * Merge pull request #615 from rapidpro/poll-list
 * Add sync schedule on opinions admin list
 * Merge pull request #616 from rapidpro/update-cssnano
 * Update cssnano to fix dot-prop vurnerable version
 * Merge pull request #614 from rapidpro/dependabot/npm_and_yarn/elliptic-6.5.3
 * Bump elliptic from 6.5.2 to 6.5.3
 * Merge pull request #612 from rapidpro/translations_django-po--master_hr_HR
 * Run code check
 * Apply translations in hr_HR

v1.1.171
----------
 * Merge pull request #608 from rapidpro/increase-recent-polls-window
 * Merge pull request #607 from Ilhasoft/feature/add-croatian-language
 * fix correct path for croatian language
 * Merge branch 'master' of https://github.com/rapidpro/ureport into feature/add-croatian-language
 * Add HR mo file
 * Merge branch 'master' of github.com:rapidpro/ureport into increase-recent-polls-window
 * Merge pull request #609 from rapidpro/dependabot/npm_and_yarn/lodash-4.17.19
 * Merge pull request #606 from rapidpro/translations_django-po--master_hr_HR
 * Bump lodash from 4.17.15 to 4.17.19
 * Increase recent polls window to 45 days
 * Enable croatian language
 * Apply translations in hr_HR
 * Apply translations in hr_HR

v1.1.170
----------
 * Merge pull request #605 from rapidpro/clear-old-results-with-lock-key
 * Grab lock before clearing old results so we do not interfere with ongoing sync

v1.1.169
----------
 * Merge pull request #604 from rapidpro/fix-bug-rebuilding-polls-stats
 * Merge pull request #603 from rapidpro/recalculate-stats
 * Only update stats for polls that are not stopped syncing
 * Trigger update results cache in a task when a poll questions are updated

v1.1.168
----------
 * Merge pull request #601 from rapidpro/update-sec

v1.1.163
----------
 * Merge pull request #600 from rapidpro/add-south-asia
 * Add South Asia flag

v1.1.162
----------
 * Merge pull request #599 from rapidpro/limit-global-map
 * Add config to limit countries on World map

v1.1.161
----------
 * Merge pull request #598 from rapidpro/fix-image-size
 * Adjust about image size

v1.1.160
----------
 * Merge pull request #597 from rapidpro/fix-arabic-design
 * Adjustments for RTL design on admin site

v1.1.159
----------
 * Merge pull request #596 from rapidpro/LB-flag
 * Add Lebanon flag

v1.1.158
----------
 * Merge pull request #593 from Ilhasoft/feature/create-contact
 * Removed unique from the uuid field of the contact model

v1.1.157
----------
 * Merge pull request #595 from rapidpro/update-django
 * Update django

v1.1.156
----------
 * Merge pull request #592 from rapidpro/update-settings
 * Update settings
 * Update README.md
 * Update CI badges
 * Merge pull request #590 from rapidpro/update-CI
 * Update CI, add code_check and format code
 * Merge branch 'master' of github.com:rapidpro/ureport
 * Update CHANGELOG.md for v1.1.155

v1.1.155
----------
 * Merge pull request #591 from rapidpro/order-categories
 * Reorder the categories

v1.1.154
----------
 * Merge pull request #589 from rapidpro/slow-queue
 * Add slow queue, fix django compressor offline context

v1.1.153
----------
 * Better message
 * Hide multiple pages for mobile
 * Improve mobile site
 * Remove unused method
 * Add migration file
 * Fix the location and age segmentation
 * Add a way to configure the display of the category for poll questions
 * Show clear feedback to admin on polls being synced

v1.1.152
----------
 * Merge pull request #583 from rapidpro/fix-locations-sync
 * Merge pull request #584 from Ilhasoft/feature/add-lesotho
 * add lesotho to ureport
 * Add ordering so we can delete to update the locations boundaries without constraint

v1.1.151
----------
 * Merge pull request #581 from rapidpro/move-task-queues
 * Move task queues

v1.1.150
----------
 * Merge pull request #580 from Ilhasoft/hotfix/fix-size-bulgaria-flag
 * Remove overflow style
 * fix size bulgaria flag

v1.1.149
----------
 * Merge pull request #579 from rapidpro/other-lang-sites
 * Include current site with a check mark
 * Add a way to link sites as connected sites in a different language

v1.1.148
----------
 * Rebuild locale
 * Merge pull request #573 from rapidpro/translations_django-po--master_uz
 * Merge pull request #572 from rapidpro/translations_django-po--master_bg
 * Merge pull request #575 from rapidpro/remove-unused-variables
 * Remove unused context variables
 * Merge pull request #574 from rapidpro/prevent-looped-run-results-overwrite
 * Only replace results with category with one which is empty if they are 5 seconds older
 * Translate /locale/en/LC_MESSAGES/django.po in uz
 * Translate /locale/en/LC_MESSAGES/django.po in bg

v1.1.147
----------
 * Fix if block

v1.1.146
----------
 * Merge pull request #570 from rapidpro/translations_django-po--master_bg
 * Rebuild locale
 * Fix conflicts
 * Merge pull request #571 from rapidpro/use-show-login
 * Rebuild locale
 * Translate /locale/en/LC_MESSAGES/django.po in bg
 * Translate /locale/en/LC_MESSAGES/django.po in bg
 * Do not show login on custom domain

v1.1.145
----------
 * Merge pull request #569 from rapidpro/support-results-without-input
 * Allo saving text for node results without reporter input

v1.1.144
----------
 * Merge pull request #568 from rapidpro/api-poll-data
 * Merge pull request #567 from Ilhasoft/feature/add-bulgaria
 * Only include the results segmentation maintained for the existing graphs
 * fix a trailing space
 * add bulgaria to ureport

v1.1.143
----------
 * Merge pull request #566 from rapidpro/fix-pill-button-broken-by-translate
 * Fix alerts
 * Fix pills button broken by translate

v1.1.142
----------
 * Update django
 * Rebuild locale
 * Merge pull request #565 from rapidpro/translations_django-po--master_bg
 * Translate /locale/en/LC_MESSAGES/django.po in bg

v1.1.141
----------
 * Merge pull request #564 from rapidpro/contacts-counts-performance
 * More tests
 * Increase cache time for contacts counts and add task to update the cache

v1.1.140
----------
 * Merge pull request #563 from rapidpro/stats-for-same-flow-polls
 * Rebuild stats for polls of the same flow at the same time

v1.1.139
----------
 * Update Burmese
 * Rebuild locale
 * Rebuild locale
 * Fix maps stats to properly count the parents stats
 * Translate /locale/en/LC_MESSAGES/django.po in bs

v1.1.138
----------
 * Merge pull request #558 from rapidpro/v1-design-remove-part3

v1.1.136
----------
 * Merge pull request #559 from rapidpro/fix-countries
 * Merge branch 'fix-countries' of github.com:rapidpro/ureport into fix-countries
 * Add countries view back
 * Add coutries view back

v1.1.135
----------
 * Merge pull request #557 from rapidpro/v1-design-remove-part2
 * Pin less to 3.10.3
 * Pin less to 3.10.3

v1.1.134
----------
 * Merge pull request #556 from rapidpro/v1-design-remove-part2
 * Merge branch 'master' of github.com:rapidpro/ureport into v1-design-remove-part2
 * Update flake8
 * Replace print statement
 * Stop using PollReporterCounter and improve the tests to be more correct

v1.1.133
----------
 * Add back the status view

v1.1.132
----------
 * Merge pull request #555 from rapidpro/v1-design-remove-part1
 * Remove V1 design templates

v1.1.131
----------
 * Merge pull request #554 from rapidpro/fix-geojson
 * Update countries geoJSON

v1.1.130
----------
 * Merge pull request #553 from rapidpro/add-fsm
 * Add FSM icon

v1.1.129
----------
 * Merge pull request #552 from rapidpro/fix-active-users-charts-data
 * Active users are stored by month only so use the date for the month

v1.1.128
----------
 * Merge pull request #551 from rapidpro/squash-stats-part-2
 * Add migrations
 * Add squash method and task

v1.1.127
----------
 * Merge pull request #550 from rapidpro/squash-stats-part-1
 * Update Django
 * Add is_squashed field to stats model
 * Update CHANGELOG.md for v1.1.126
 * Merge pull request #549 from rapidpro/remove-ca
 * Remove CA flag

v1.1.126
----------
 * Merge pull request #549 from rapidpro/remove-ca
 * Remove CA flag

v1.1.125
----------
 * Merge pull request #547 from rapidpro/pacific-flag
 * Add Pacific flag
 * Update CHANGELOG.md for v1.1.124
 * Rebuild locales, with symlinks
 * Rebuild locales
 * Rebuild locales
 * Rebuild locales
 * Rebuild locales
 * Compile messages
 * Merge pull request #546 from rapidpro/fix-flags
 * Merge pull request #544 from rapidpro/translations_django-po--master_bs
 * Add Botswana flag, fix links properly
 * Translate /locale/en/LC_MESSAGES/django.po in bs

v1.1.124
----------
 * Rebuild locales, with symlinks
 * Rebuild locales
 * Rebuild locales
 * Rebuild locales
 * Rebuild locales
 * Compile messages
 * Merge pull request #546 from rapidpro/fix-flags
 * Merge pull request #544 from rapidpro/translations_django-po--master_bs
 * Add Botswana flag, fix links properly
 * Translate /locale/en/LC_MESSAGES/django.po in bs

v1.1.123
----------
 * Update JS deps
 * Rebuild locales
 * Merge pull request #538 from Ilhasoft/update/costa-rica-flag
 * Merge pull request #540 from rapidpro/translations_django-po--master_ro
 * Translate /locale/en/LC_MESSAGES/django.po in ro
 * Added flag for Costa Rica

v1.1.122
----------
 * Rebuild locales
 * Merge pull request #534 from rapidpro/translations_django-po--master_pt_BR
 * Merge pull request #537 from rapidpro/deps-update
 * Merge pull request #536 from Ilhasoft/fixing/new-behaviour-in-python-3.7
 * Update deps
 * Adjustments on chunk_list(iterable, size), to avoid a runtime error 'generator raised StopIteration'
 * Apply translations in pt_BR

v1.1.121
----------
 * Include GA on the v2 public site

v1.1.120
----------
 * Merge pull request #535 from rapidpro/fix-poll-gender-for-gender-custom-labels
 * Fix gender stats with custom gender labels

v1.1.119
----------
 * Merge pull request #533 from Ilhasoft/hotfix/img_sizing_on_stories_v1
 * Fixing on image responsivity while scaling large images on story detail

v1.1.118
----------
 * Merge pull request #521 from rapidpro/old-poll-results-clear
 * Fix conflicts and merge master
 * Rebuild locale
 * Merge pull request #532 from rapidpro/translations_django-po--master_sr_RS@latin
 * Merge branch 'master' into translations_django-po--master_sr_RS@latin
 * Merge pull request #527 from Ilhasoft/feature/enable_serbian_latin_serbia_language
 * Apply translations in sr_RS@latin
 * remove sr_latn from languages on settings_common
 * enable locale for Serbian Latin Serbia language

v1.1.116
----------
 * Merge pull request #531 from rapidpro/language-fix
 * Make sure we have the org language activated for precalculated data

v1.1.115
----------
 * Rebuild locale
 * Merge pull request #526 from Ilhasoft/hotfix/limit-poll-states
 * Merge pull request #530 from rapidpro/rebuild-locale
 * Fix poll page graph reload and sort locations options
 * Rebuild locale
 * Rebuild locale
 * Update form fields size for superadmin in v1
 * Update form fields size for superadmin
 * Add limit poll states config for superusers

v1.1.114
----------
 * Merge pull request #528 from rapidpro/fix-engagement-data-to-ignore-inactive-questions
 * Merge pull request #529 from rapidpro/update-locale-arabic
 * Add Jordan flag
 * Rebuild locale
 * Update Arabic, rebuild locale
 * Filter for active questions on the engagement data

v1.1.113
----------
 * Add mo files
 * Merge pull request #525 from rapidpro/arabic-locale
 * Rebuild locale
 * Rebuild locale
 * Update Arabic translations
 * Rebuild locale
 * Merge pull request #522 from rapidpro/translations_django-po--master_sr_RS@latin
 * Merge pull request #524 from Quality-Management/bugfix/socialwidget
 * Fixed class name
 * Fixed class for widget error
 * fixed parameter when only one social media widget is used
 * Apply translations in sr_RS@latin

v1.1.112
----------
 * Merge pull request #520 from rapidpro/add-canada-flag
 * Add Canada flag

v1.1.111
----------
 * Remove New Zealand flag

v1.1.110
----------
 * Merge pull request #519 from rapidpro/fix-global-count
 * Add Bengali language option
 * Fix global count

v1.1.109
----------
 * Fix typo

v1.1.108
----------
 * Merge pull request #518 from rapidpro/remove-syria-flag
 * Remove Syria flag and fix chooser flags

v1.1.107
----------
 * Merge pull request #517 from rapidpro/country-flags-common
 * Countries count are for sites that are for the country entirely

v1.1.105
----------
 * Rebuild locales
 * Rebuild locales
 * Merge pull request #509 from rapidpro/translations_django-po--master_bn
 * Translate /locale/en/LC_MESSAGES/django.po in bn
 * Merge pull request #508 from rapidpro/max-upload-size
 * Increase max size allowed to upload to 10MB

v1.1.104
----------
 * Merge pull request #507 from rapidpro/limit-opinion-responses-by-date
 * Precalculate the avearage response for the engagement page

v1.1.103
----------
 * Merge pull request #506 from rapidpro/limit-opinion-responses-by-date
 * Limit all opinions response to the last year

v1.1.102
----------
 * Merge pull request #504 from rapidpro/counters-config
 * Merge pull request #505 from rapidpro/fix-countries-number
 * Add way to sync counts from all providers for orgs that do not display flags
 * Update rebuild counts to include older polls too
 * Fix the query for number for countries on homepage

v1.1.101
----------
 * Fix Facebook share URL

v1.1.100
----------
 * Merge pull request #503 from rapidpro/translations-1
 * Add callback for summernote to hints user the file is big
 * Rebuild locales
 * Rebuild locales
 * Add translations manually

v1.1.99
----------
 * Add tests
 * Fix poll stats without date

v1.1.98
----------
 * Merge pull request #502 from rapidpro/add-indexes

v1.1.96
----------
 * Disable the squash for reporters counters

v1.1.95
----------
 * Refresh engagement data once a day

v1.1.94
----------
 * Add overflow scroll on longer labels

v1.1.93
----------
 * Use HTML for hightcharts labels

v1.1.92
----------
 * Merge pull request #501 from rapidpro/calculate-results-poll-stats-2
 * Show day in tooltip date
 * Show day in tooltip date
 * Show up to 3 points per month for 3 months charts
 * Merge branch 'calculate-results-poll-stats' of github.com:rapidpro/ureport into calculate-results-poll-stats-2
 * Merge branch 'master' of github.com:rapidpro/ureport into calculate-results-poll-stats-2
 * Fix date key lookup
 * Use smaller intervals for small time filters on engagement

v1.1.90
----------
 * Merge pull request #484 from rapidpro/calculate-results-poll-stats

v1.1.89
----------
 * Add back some hover background with static colors
 * Rebuild locales

v1.1.88
----------
 * Rebuild locales
 * Merge pull request #500 from rapidpro/avoid-compressor-context-loop
 * Rebuild locales
 * More charts localizations
 * Fix typo
 * Add if block for admin site

v1.1.83
----------


v1.1.82
----------
 * Fix links

v1.1.81
----------
 * Merge pull request #499 from rapidpro/stories-og-tags
 * Add open graph tags for facebook image sharing on story page

v1.1.80
----------
 * Rebuild locales
 * Merge pull request #498 from rapidpro/translations_django-po--master_fr
 * Translate /locale/en/LC_MESSAGES/django.po in fr

v1.1.79
----------
 * Rebuild locales
 * Rebuild locales
 * Merge pull request #496 from rapidpro/translations_django-po--master_es
 * Merge pull request #497 from Ilhasoft/translations_django-po--master_es
 * Merge remote-tracking branch 'rapidpro/master' into translations_django-po--master_es
 * Translate /locale/en/LC_MESSAGES/django.po in es

v1.1.78
----------
 * Merge pull request #494 from rapidpro/argentina-bugs
 * Revert join now changes
 * Rebuild locales
 * Fixes social media new tabs, polls and stories order, age chart fix

v1.1.77
----------
 * Merge pull request #493 from rapidpro/fr-trans
 * Rebuild locales
 * Fix tests
 * Rebuild locales
 * No jobs page if not configured
 * Manual FR updates

v1.1.76
----------
 * Rebuild locales
 * Merge pull request #486 from Ilhasoft/fix/static
 * Rebuild locales
 * Merge pull request #492 from rapidpro/translations_django-po--master_it
 * Translate /locale/en/LC_MESSAGES/django.po in it
 * Added "sitestatic" in middleware

v1.1.75
----------
 * Rebuild locales
 * Merge pull request #491 from rapidpro/fr-trans
 * Rebuild locales
 * Merge branch 'master' of github.com:rapidpro/ureport into fr-trans
 * Merge pull request #490 from rapidpro/translations_djangojs-po--master_fr_FR
 * Update FR translations
 * Apply translations in fr_FR

v1.1.74
----------
 * Merge pull request #489 from rapidpro/admin-links
 * REduce more longer titles
 * Merge pull request #488 from rapidpro/admin-links
 * rebuild locales
 * Merge master
 * Merge pull request #487 from rapidpro/translations_django-po--master_es
 * Rebuild locales
 * Change bg color on hover
 * Rebuild locales
 * Merge branch 'master' into translations_django-po--master_es
 * Translate /locale/en/LC_MESSAGES/django.po in es
 * Rebuild locales
 * Improve admin links to be noticeable

v1.1.73
----------
 * Fix to force label shows on all chart bars

v1.1.72
----------
 * Merge pull request #485 from rapidpro/bugs-fix
 * Auto rotate labels on opinion page
 * Update FB SDK version
 * Fix iframe styles
 * Fix date format
 * Fix the calculation of average response to be all time, not last year
 * Add South Africa static flag config
 * Merge pull request #483 from Ilhasoft/fix/api-page
 * Fix css/js

v1.1.71
----------
 * Merge pull request #482 from rapidpro/beta-fixes
 * Rebuild locales
 * Fix modal scrolling behavior

v1.1.70
----------
 * Allow status view without org

v1.1.69
----------
 * Merge pull request #481 from rapidpro/status-view
 * Add status view

v1.1.68
----------
 * Merge pull request #480 from rapidpro/beta-fixes
 * consistent read more button
 * Fix stories button hover state, and screenshot modal z-index

v1.1.67
----------
 * Screenshot modal position

v1.1.66
----------
 * Fix polls maps

v1.1.65
----------
 * Use center bottom to redraw

v1.1.64
----------
 * Use top-bottom anchor to trigger redraw

v1.1.63
----------
 * Merge pull request #479 from rapidpro/beta-fixes

v1.1.61
----------
 * Hide photos section if no photos can be displayed

v1.1.60
----------
 * Merge pull request #478 from rapidpro/beta-fixes
 * Add select country image
 * Add select country image
 * Update CHANGELOG.md for v1.1.59
 * Merge pull request #476 from rapidpro/beta-fixes

v1.1.59
----------
 * Merge pull request #476 from rapidpro/beta-fixes
 * Move anchor placement to top center for aos and trigger redraw fast
 * Add migration to add photo blocks type
 * Rebuild locales

v1.1.47
----------
 * Adjuts jobs page
 * Larger circles
 * Merge pull request #473 from rapidpro/beta-fixes
 * Refresh AOS

v1.1.45
----------
 * Merge pull request #472 from rapidpro/fix-stats
 * Merge branch 'master' of github.com:rapidpro/ureport into fix-stats
 * Merge pull request #471 from rapidpro/poll-date-api
 * Merge pull request #470 from rapidpro/beta-fixes
 * Add timeout to lock of poll counts rebuild
 * Add poll date to API

v1.1.38
----------
 * Show top region on maps
 * state pill label to STATE
 * lighten button backgrounds on hover
 * Fix social media switching buttons
 * Reduce line height on poll title on homepage
 * Add bottom border on navbar

v1.1.37
----------
 * Merge pull request #469 from rapidpro/beta-fixes
 * Fix crop argument
 * Add spinner on maps before they load
 * Full width on engagement page
 * Adjust label font weight on opinions page
 * Hide question number on screenshot capture

v1.1.36
----------
 * Merge pull request #467 from rapidpro/edit-blocks
 * Fix tests
 * Merge pull request #465 from rapidpro/translations_djangojs-po--master_my
 * Translate locale/en/LC_MESSAGES/djangojs.po in my

v1.1.34
----------
 * Increment after using the color

v1.1.33
----------
 * Merge pull request #466 from rapidpro/beta-fixes
 * Fix conflicting colors for state segmentation

v1.1.27
----------
 * Fix admin navbar

v1.1.26
----------
 * Quick fixes

v1.1.25
----------
 * Merge pull request #461 from rapidpro/RTL-support
 * Merge pull request #462 from rapidpro/use-cached-results
 * Really fix conflicts and merge
 * Use cached results
 * Use cached results
 * fix conflicts and merge
 * update locales
 * tweak styles for admin nav

v1.1.19
----------
 * Add social media tab icons

v1.1.18
----------
 * Align text in the left boxes with the left angle applied too

v1.1.17
----------
 * Merge pull request #458 from rapidpro/engagement-charts

v1.1.8
----------
 * Adjust cursor and sticky bar
 * Merge pull request #451 from rapidpro/layout-tweaks
 * age graph pane only 1/2
 * livvic as alt font
 * montserrat as alt font
 * fix mobile menu spacing
 * about page
 * new global layouts
 * new layouyg
 * transition menu with slide

v1.1.6
----------


v1.1.5
----------
 * Merge pull request #444 from rapidpro/admin-nav-public-site
 * labels for age charts
 * Extra utility classes for the admin menu links
 * better segmented labeling
 * fix top logo
 * rebuild locales
 * Add admin navbar on top on public site
 * Merge branch 'master' of github.com:rapidpro/ureport into admin-nav-public-site
 * Merge pull request #443 from rapidpro/locale-fix
 * Makemessages and compile messages
 * WIP admin navbar for public site
 * Merge branch 'master' of github.com:rapidpro/ureport into locale-fix
 * Makemessages and compile messages
 * Merge pull request #442 from rapidpro/uikit
 * Rebuild locale
 * Merge pull request #428 from rapidpro/css-tweaks
 * Merge pull request #441 from rapidpro/tailwind-design
 * Fix SASS countries background
 * Only allow search engines on the rigth domains
 * Merge master
 * Update CHANGELOG.md for v1.1.4
 * Merge pull request #440 from rapidpro/fix-org-counts
 * Fix contacts triggers to not consider contacts with is_active False
 * Fix recalculate to ignore contact not active
 * Update CHANGELOG.md for v1.1.3
 * Merge pull request #436 from rapidpro/revert-maps-file
 * Fix script name
 * Revert leaflet library
 * Revert maps change to keep supporting properly the old version
 * Update CHANGELOG.md for v1.1.2
 * Ignore node_mudules
 * Merge pull request #434 from rapidpro/fix-design
 * Fix endif tag place
 * Update CHANGELOG.md for v1.1.1
 * Merge pull request #433 from rapidpro/post-deploy-fixes
 * More adjustements
 * Remove placeholders and adjust logos
 * Update CHANGELOG.md for v1.1.0
 * Merge pull request #432 from rapidpro/uikit

v1.1.4
----------
 * Fix contacts triggers to not consider contacts with is_active False
 * Fix recalculate to ignore contact not active

v1.1.3
----------
 * Revert leaflet library
 * Revert maps change to keep supporting properly the old version

v1.1.2
----------
 * Ignore node_mudules
 * Fix endif tag place

v1.1.1
----------
 * Merge pull request #433 from rapidpro/post-deploy-fixes
 * More adjustements
 * Remove placeholders and adjust logos

v1.1.0
----------
 * Merge pull request #432 from rapidpro/uikit

v1.0.459
----------
 * Fix staging DATABASES config

v1.0.458
----------
 * Merge pull request #420 from rapidpro/contact-activity
 * Merge pull request #419 from rapidpro/poll-stats

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

