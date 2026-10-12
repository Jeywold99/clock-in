from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from tracker.models import TimeEntry

from .utils import make_entry, make_project, make_user, utc


class TimerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("alice")
        cls.project = make_project(rate="80.00")

    def setUp(self):
        self.client.force_login(self.user)

    def start(self, **extra):
        return self.client.post(
            reverse("timer_start"), {"project": self.project.pk, "description": "Work", **extra}
        )

    def test_start_creates_running_entry_with_rate_snapshot(self):
        response = self.start()
        self.assertRedirects(response, reverse("dashboard"))
        entry = TimeEntry.objects.get()
        self.assertTrue(entry.is_running)
        self.assertEqual(entry.rate_applied, Decimal("80.00"))
        self.assertTrue(entry.is_billable)

    def test_non_billable_project_defaults_apply(self):
        internal = make_project(client_name="Internal", name="Ops", rate=None,
                                billable_default=False)
        self.client.post(reverse("timer_start"), {"project": internal.pk, "description": ""})
        entry = TimeEntry.objects.get()
        self.assertFalse(entry.is_billable)
        self.assertIsNone(entry.rate_applied)

    def test_second_start_is_rejected_gracefully(self):
        self.start()
        response = self.start()
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(TimeEntry.objects.running().count(), 1)

    def test_stop_finishes_entry_and_end_is_after_start(self):
        self.start()
        response = self.client.post(reverse("timer_stop"))
        self.assertRedirects(response, reverse("dashboard"))
        entry = TimeEntry.objects.get()
        self.assertFalse(entry.is_running)
        # The clamp guarantees this even for an instant stop.
        self.assertGreater(entry.ended_at, entry.started_at)

    def test_stop_without_running_timer_is_harmless(self):
        response = self.client.post(reverse("timer_stop"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_discard_deletes_running_entry(self):
        self.start()
        response = self.client.post(reverse("timer_discard"))
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_discard_does_not_touch_finished_entries(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        self.client.post(reverse("timer_discard"))
        self.assertEqual(TimeEntry.objects.count(), 1)

    def test_timer_endpoints_require_post(self):
        for name in ("timer_start", "timer_stop", "timer_discard"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 405)

    def test_timer_endpoints_require_login(self):
        self.client.logout()
        response = self.client.post(reverse("timer_stop"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
