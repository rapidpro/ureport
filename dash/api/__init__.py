import json
import urllib
import requests

from django.core.cache import cache
from django.conf import settings
from django.utils.text import slugify

from redis_cache import get_redis_connection

# level constants
COUNTRY = 0
STATE = 1
DISTRICT = 2

# we cache boundary data for a month at a time
BOUNDARY_CACHE_TIME = getattr(settings, 'API_BOUNDARY_CACHE_TIME', 60 * 60 * 24 * 30)

# five minutes for group cache
GROUP_CACHE_TIME = getattr(settings, 'API_GROUP_CACHE_TIME', 300)

# fifteen minutes for result cache
RESULT_CACHE_TIME = getattr(settings, 'API_RESULT_CACHE_TIME', 900)

class API(object):

    def __init__(self, org):
        self.org = org

    def clear_caches(self):
        # using raw redis we go remove keys
        r = get_redis_connection('default')

        keys = r.keys('group:%d:*' % self.org.id)
        r.delete(keys)

        keys = r.keys('geojson:%d' % self.org.id)
        r.delete(keys)

        keys = r.keys('geojson:%d:' % self.org.id)
        r.delete(keys)

        keys = r.keys('rs:%d:' % self.org.id)
        r.delete(keys)

        keys = r.keys('cf:%d:' % self.org.id)
        r.delete(keys)

        keys = r.keys('flows:%d' % self.org.id)
        r.delete(keys)

    def get_group(self, name):
        cache_key = 'group:%d:%s' % (self.org.id, slugify(name))
        group = cache.get(cache_key)

        if not group:
            response = requests.get('%s/api/v1/groups.api' % settings.API_ENDPOINT,
                                    params={'name': name},
                                    headers={'Content-type': 'application/json',
                                             'Accept': 'application/json',
                                             'Authorization': 'Token %s' % self.org.api_token})
            result = response.json()
            group = result['results'][0]

            cache.set(cache_key, group, GROUP_CACHE_TIME)

        return group

    def get_country_geojson(self):
        cache_key = 'geojson:%d' % self.org.id
        states = cache.get(cache_key)

        if not states:
            cached = self.build_boundaries()
            states = cached.get(cache_key, None)

        return states

    def get_state_geojson(self, state_id):
        cache_key = 'geojson:%d:%s' % (self.org.id, state_id)
        districts = cache.get(cache_key)

        if not districts:
            cached = self.build_boundaries()
            districts = cached.get(cache_key, None)

        return districts

    def build_boundaries(self):
        next = '%s/api/v1/boundaries.json' % settings.API_ENDPOINT
        boundaries = []

        while next:
            response = requests.get(next,
                                    headers={'Content-type': 'application/json',
                                             'Accept': 'application/json',
                                             'Authorization': 'Token %s' % self.org.api_token})

            result = response.json()

            for boundary in result['results']:
                boundaries.append(boundary)

            next = result['next']

        # we now build our cached versions of level 1 (all states) and level 2 (all districts for each state) geojson
        states = []
        districts_by_state = dict()
        for boundary in boundaries:
            if boundary['level'] == STATE:
                states.append(boundary)
            elif boundary['level'] == DISTRICT:
                osm_id = boundary['parent']
                if not osm_id in districts_by_state:
                    districts_by_state[osm_id] = []

                districts = districts_by_state[osm_id]
                districts.append(boundary)

        # mini function to convert a list of boundary objects to geojson
        def to_geojson(boundary_list):
            features = [dict(type='Feature', geometry=b['geometry'],
                             properties=dict(name=b['name'], id=b['boundary'], level=b['level'])) for b in boundary_list]
            return dict(type='FeatureCollection', features=features)

        cached = dict()

        # save our cached geojson to redis
        cache.set('geojson:%d' % self.org.id, to_geojson(states), BOUNDARY_CACHE_TIME)
        cached['geojson:%d' % self.org.id] = to_geojson(states)

        for state_id in districts_by_state.keys():
            cache.set('geojson:%d:%s' % (self.org.id, state_id), to_geojson(districts_by_state[state_id]), BOUNDARY_CACHE_TIME)
            cached['geojson:%d:%s' % (self.org.id, state_id)] = to_geojson(districts_by_state[state_id])

        return cached

    def get_ruleset_results(self, ruleset_id, segment=None):
        cache_key = 'rs:%s:%d' % (self.org.id, ruleset_id)

        if segment:
            # if our segment is on location, remap the location from the static 'State' and 'District' to the actual labels
            location = segment.get('location', None)
            if location == 'State':
                segment['location'] = self.org.get_config('state_label')
            elif location == 'District':
                segment['location'] = self.org.get_config('district_label')

            cache_key += ":" + slugify(unicode(json.dumps(segment)))

        results = cache.get(cache_key)

        if not results:
            url = '%s/api/v1/results.json?ruleset=%d&segment=%s' % (settings.API_ENDPOINT, ruleset_id,
                                                                    urllib.quote(unicode(json.dumps(segment)).encode('utf8')))
            response = requests.get(url,
                                    headers={'Content-type': 'application/json',
                                             'Accept': 'application/json',
                                             'Authorization': 'Token %s' % self.org.api_token})

            results = response.json()['results']
            cache.set(cache_key, results, RESULT_CACHE_TIME)

        return results

    def get_contact_field_results(self, contact_field_label, segment=None):
        cache_key = 'cf:%d:%s' % (self.org.id, slugify(contact_field_label))

        if segment:
            # if our segment is on location, remap the location from the static 'State' and 'District' to the actual labels
            location = segment.get('location', None)
            if location == 'State':
                segment['location'] = self.org.get_config('state_label')
            elif location == 'District':
                segment['location'] = self.org.get_config('district_label')

            cache_key += ":" + slugify(unicode(json.dumps(segment)))

        results = cache.get(cache_key)

        if not results:
            response = requests.get('%s/api/v1/results.json?contact_field=%s&segment=%s' % (settings.API_ENDPOINT, contact_field_label, urllib.quote(unicode(json.dumps(segment)).encode('utf8'))),
                                    headers={'Content-type': 'application/json',
                                             'Accept': 'application/json',
                                             'Authorization': 'Token %s' % self.org.api_token})

            results = response.json()['results']
            cache.set(cache_key, results, 3600)

        return results

    def get_flow(self, flow_id):
        return self.get_flows("flow=%d" % flow_id)[0]

    def get_flows(self, filter=None):
        cache_key = 'flows:%d' % self.org.id
        next = '%s/api/v1/flows.json' % settings.API_ENDPOINT

        # munge our cache key and filter if necessary
        if filter:
            cache_key += ":" + filter
            next += "?" + filter

        flows = cache.get(cache_key)

        if not flows:
            flows = []

            while next:
                response = requests.get(next,
                                        headers={'Content-type': 'application/json',
                                                 'Accept': 'application/json',
                                                 'Authorization': 'Token %s' % self.org.api_token})

                result = response.json()

                # we only include flows that have one or more rules
                for flow in result['results']:
                    if len(flow['rulesets']) > 0:
                        flows.append(flow)

                next = result['next']

            # save to our cache for fifteen minutes
            cache.set(cache_key, flows, RESULT_CACHE_TIME)

        return flows
