from ureport.polls.models import Poll
from django.http import JsonResponse


def get_flow_info(request, poll_id):
    flow_exists = Poll.objects.filter(id=poll_id).exists()
    if flow_exists:
        flow = Poll.objects.get(id=poll_id)
        return JsonResponse({
            'poll_id': poll_id,
            'flow_uuid': flow.flow_uuid,
            'title': flow.title
        })
    else:
        return JsonResponse({
            'poll_id': 0,
            'flow_uuid': 0,
            'title': None
        })
