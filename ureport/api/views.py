from ureport.polls.models import Poll
from django.http import JsonResponse, HttpResponseNotFound


def get_flow_info(request, poll_id):
    flow = Poll.objects.filter(id=poll_id).first()
    if flow:
        return JsonResponse({
            'poll_id': poll_id,
            'flow_uuid': flow.flow_uuid,
            'title': flow.title
        })
    else:
        return HttpResponseNotFound('<h1>Page not found</h1>')
