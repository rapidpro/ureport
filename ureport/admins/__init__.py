from dash.orgs.models import Org
from enum import Enum
from ureport.polls.tasks import refresh_main_poll, refresh_brick_polls, refresh_other_polls, refresh_org_flows
from ureport.polls.tasks import refresh_org_graphs_data, refresh_org_reporters


class OrgCache(Enum):
    boundaries = 1
    main_polls = 2
    brick_polls = 3
    other_polls = 4
    flows = 5
    reporters = 6
    graphs_data = 7


def refresh_caches(org, caches):
    if not org:
        return

    if OrgCache.boundaries in caches:
        Org.rebuild_org_boundaries_task(org)

    if OrgCache.main_polls in caches:
        refresh_main_poll.delay(org.pk)

    if OrgCache.brick_polls in caches:
        refresh_brick_polls.delay(org.pk)

    if OrgCache.other_polls in caches:
        refresh_other_polls.delay(org.pk)

    if OrgCache.flows in caches:
        refresh_org_flows.delay(org.pk)

    if OrgCache.reporters in caches:
        refresh_org_reporters.delay(org.pk)

    if OrgCache.graphs_data in caches:
        refresh_org_graphs_data.delay(org.pk)
