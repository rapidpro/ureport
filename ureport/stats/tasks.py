import logging
import time

from dash.orgs.tasks import org_task

logger = logging.getLogger(__name__)


@org_task("refresh-engagement-data", 60 * 60)
def refresh_engagement_data(org, since, until):
    from .models import PollStats

    start = time.time()

    time_filters = list(PollStats.DATA_TIME_FILTERS.keys())
    segments = list(PollStats.DATA_SEGMENTS.keys())
    metrics = list(PollStats.DATA_METRICS.keys())

    for time_filter in time_filters:
        for segment in segments:
            for metric in metrics:
                PollStats.refresh_engagement_data(org, metric, segment, time_filter)
                logger.info(
                    f"Task: refresh_engagement_data in progress for {time.time() - start}s, for time_filter - {time_filter}, segment - {segment}, metric - {metric}"
                )

    PollStats.calculate_average_response_rate(org)

    logger.info(f"Task: refresh_engagement_data finished in {time.time() - start}s")
