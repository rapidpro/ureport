from dash.orgs.models import Org
from enum import Enum
from ureport.locations.models import Boundary
from ureport.polls.tasks import refresh_org_flows


class OrgCache(Enum):
    boundaries = 1
    main_polls = 2
    brick_polls = 3
    other_polls = 4
    flows = 5
    recent_reporters = 6
    all_reporters = 7


def refresh_caches(org, caches):

    if OrgCache.flows in caches:
        refresh_org_flows.delay(org.pk)
