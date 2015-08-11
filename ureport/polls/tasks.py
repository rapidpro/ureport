import logging

from djcelery.app import app


logger = logging.getLogger(__name__)


@app.task(track_started=True, name='fetch_poll')
def fetch_poll(poll_id):
    try:
        # get our poll
        from .models import Poll
        poll = Poll.objects.get(pk=poll_id)
        poll.fetch_poll_results()
    except Exception as e:
        logger.exception("Error fetching poll results: %s" % str(e))
