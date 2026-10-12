"""Timezone correctness: input parsed in the user's zone, storage in UTC,
DST transitions, and local-day bucketing in lists and the timesheet."""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from tracker.models import TimeEntry

from .utils import make_entry, make_project, make_user, utc


def form_data(project, started, ended):
    return {
        "project": project.pk,
        "description": "tz test",
        "started_at": started,
        "ended_at": ended,
        "is_billable": "on",
        "rate_applied": "",
    }


class InputTimezoneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manila_user = make_user("manila", tz="Asia/Manila")  # UTC+8, no DST
        cls.ny_user = make_user("newyork", tz="America/New_York")
        cls.project = make_project()

    def test_times_parsed_in_users_zone_and_stored_utc(self):
        self.client.force_login(self.manila_user)
        self.client.post(
            reverse("entry_create"),
            form_data(self.project, "2026-07-06T09:00", "2026-07-06T10:00"),
        )
        entry = TimeEntry.objects.get()
        self.assertEqual(entry.started_at, utc(2026, 7, 6, 1))  # 09:00 Manila == 01:00 UTC
        self.assertEqual(entry.ended_at, utc(2026, 7, 6, 2))

    def test_edit_form_displays_times_in_users_zone(self):
        entry = make_entry(self.manila_user, self.project, utc(2026, 7, 6, 1), utc(2026, 7, 6, 2))
        self.client.force_login(self.manila_user)
        response = self.client.get(reverse("entry_edit", args=[entry.pk]))
        self.assertContains(response, 'value="2026-07-06T09:00"')

    def test_spring_forward_duration(self):
        # US DST starts 2026-03-08: 02:00 EST jumps to 03:00 EDT, so
        # 01:30 -> 03:30 wall-clock is only 1 real hour.
        self.client.force_login(self.ny_user)
        self.client.post(
            reverse("entry_create"),
            form_data(self.project, "2026-03-08T01:30", "2026-03-08T03:30"),
        )
        entry = TimeEntry.objects.get()
        self.assertEqual(entry.duration, timedelta(hours=1))

    def test_fall_back_duration_with_unambiguous_times(self):
        # US DST ends 2026-11-01 (02:00 EDT falls back to 01:00 EST).
        # 23:30 Sat -> 00:30 Sun avoids the repeated hour entirely.
        self.client.force_login(self.ny_user)
        self.client.post(
            reverse("entry_create"),
            form_data(self.project, "2026-10-31T23:30", "2026-11-01T00:30"),
        )
        entry = TimeEntry.objects.get()
        self.assertEqual(entry.duration, timedelta(hours=1))

    def test_ambiguous_fall_back_time_is_rejected_not_guessed(self):
        # 01:30 on 2026-11-01 happens twice in America/New_York. Django
        # refuses to guess which one was meant and asks the user instead.
        self.client.force_login(self.ny_user)
        response = self.client.post(
            reverse("entry_create"),
            form_data(self.project, "2026-11-01T01:30", "2026-11-01T03:00"),
        )
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertContains(response, "couldn’t be interpreted in time zone")

    def test_nonexistent_spring_forward_time_is_rejected(self):
        # 02:30 on 2026-03-08 never happens in America/New_York.
        self.client.force_login(self.ny_user)
        response = self.client.post(
            reverse("entry_create"),
            form_data(self.project, "2026-03-08T02:30", "2026-03-08T04:00"),
        )
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertContains(response, "couldn’t be interpreted in time zone")


class LocalDayBucketingTests(TestCase):
    """An entry near midnight belongs to the user's local day, not UTC's."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("manila", tz="Asia/Manila")
        cls.project = make_project()
        # 07:00 Tue 7 Jul in Manila == 23:00 Mon 6 Jul UTC.
        cls.entry = make_entry(
            cls.user, cls.project, utc(2026, 7, 6, 23), utc(2026, 7, 7, 0)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_entry_list_date_filter_uses_local_date(self):
        response = self.client.get(reverse("entry_list"), {"from": "2026-07-07", "to": "2026-07-07"})
        self.assertContains(response, "tz test" if False else "07:00")  # listed on the 7th
        response = self.client.get(reverse("entry_list"), {"from": "2026-07-06", "to": "2026-07-06"})
        self.assertNotContains(response, "07:00")  # not listed on the 6th

    def test_timesheet_buckets_entry_into_local_day(self):
        response = self.client.get(reverse("report_timesheet"), {"week": "2026-07-06"})
        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        days = rows[0]["days"]
        self.assertEqual(days[date(2026, 7, 7)], timedelta(hours=1))  # local Tuesday
        self.assertEqual(days[date(2026, 7, 6)], timedelta())  # not UTC Monday
