from zoneinfo import ZoneInfo

from django.utils import timezone


class TimezoneMiddleware:
    """Render and parse all datetimes in the logged-in user's timezone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                timezone.activate(ZoneInfo(request.user.timezone))
            except (KeyError, ValueError):
                timezone.deactivate()
        else:
            timezone.deactivate()
        return self.get_response(request)
