from dash.orgs.models import Org
from enum import Enum
from ureport.locations.models import Boundary
from ureport.contacts.tasks import fetch_contacts_task
from ureport.polls.tasks import refresh_main_poll, refresh_brick_polls, refresh_other_polls, refresh_org_flows
from ureport.polls.tasks import refresh_org_graphs_data, refresh_org_reporters


class OrgCache(Enum):
    boundaries = 1
    main_polls = 2
    brick_polls = 3
    other_polls = 4
    flows = 5
    recent_reporters = 6
    all_reporters = 7


def refresh_caches(org, caches):

    if OrgCache.boundaries in caches:
        Boundary.fetch_boundaries(org)

    if OrgCache.main_polls in caches:
        refresh_main_poll.delay(org.pk)

    if OrgCache.brick_polls in caches:
        refresh_brick_polls.delay(org.pk)

    if OrgCache.other_polls in caches:
        refresh_other_polls.delay(org.pk)

    if OrgCache.flows in caches:
        refresh_org_flows.delay(org.pk)

    if OrgCache.recent_reporters in caches:
        fetch_contacts_task.delay(org.pk)

    if OrgCache.all_reporters in caches:
        fetch_contacts_task.delay(org.pk, True)
