from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model

from tracker.models import Client, Project, TimeEntry


def make_user(username, *, role="member", tz="UTC", password="test-pass-123"):
    return get_user_model().objects.create_user(
        username=username, password=password, role=role, timezone=tz
    )


def make_project(*, client_name="Acme", name="Website", rate="100.00", currency="USD",
                 billable_default=True):
    client, _ = Client.objects.get_or_create(
        name=client_name, defaults={"currency": currency}
    )
    return Project.objects.create(
        client=client,
        name=name,
        hourly_rate=Decimal(rate) if rate is not None else None,
        is_billable_default=billable_default,
    )


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=dt_timezone.utc)


def make_entry(user, project, start, end=None, *, billable=True, rate=None, description=""):
    return TimeEntry.objects.create(
        user=user,
        project=project,
        description=description,
        started_at=start,
        ended_at=end,
        is_billable=billable,
        rate_applied=Decimal(rate) if rate is not None else None,
    )
