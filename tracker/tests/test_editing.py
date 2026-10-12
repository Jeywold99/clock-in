"""Tests for creating and editing time entries through the views —
the overlap warn-then-confirm flow and role scoping on edits."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from tracker.models import TimeEntry

from .utils import make_entry, make_project, make_user, utc


def entry_form_data(project, **overrides):
    data = {
        "project": project.pk,
        "description": "Some work",
        "started_at": "2026-07-06T09:00",
        "ended_at": "2026-07-06T10:00",
        "is_billable": "on",
        "rate_applied": "",
    }
    data.update(overrides)
    return data


class EntryCreateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("alice")  # timezone UTC, so form times == stored times
        cls.project = make_project(rate="100.00")

    def setUp(self):
        self.client.force_login(self.user)

    def test_create_manual_entry(self):
        response = self.client.post(reverse("entry_create"), entry_form_data(self.project))
        self.assertRedirects(response, reverse("entry_list"))
        entry = TimeEntry.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.started_at, utc(2026, 7, 6, 9))
        self.assertEqual(entry.ended_at, utc(2026, 7, 6, 10))

    def test_blank_rate_snapshots_project_rate(self):
        self.client.post(reverse("entry_create"), entry_form_data(self.project))
        self.assertEqual(TimeEntry.objects.get().rate_applied, Decimal("100.00"))

    def test_explicit_rate_wins_over_project_rate(self):
        self.client.post(
            reverse("entry_create"), entry_form_data(self.project, rate_applied="55.00")
        )
        self.assertEqual(TimeEntry.objects.get().rate_applied, Decimal("55.00"))

    def test_manual_entry_requires_end_time(self):
        response = self.client.post(
            reverse("entry_create"), entry_form_data(self.project, ended_at="")
        )
        self.assertContains(response, "End time is required")
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_end_before_start_rejected(self):
        response = self.client.post(
            reverse("entry_create"),
            entry_form_data(self.project, started_at="2026-07-06T10:00",
                            ended_at="2026-07-06T09:00"),
        )
        self.assertContains(response, "End time must be after start time")
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_overlap_shows_warning_instead_of_saving(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9, 30), utc(2026, 7, 6, 11))
        response = self.client.post(reverse("entry_create"), entry_form_data(self.project))
        self.assertContains(response, "Save anyway")
        self.assertContains(response, "1 existing entry")
        self.assertEqual(TimeEntry.objects.count(), 1)  # nothing new saved

    def test_confirm_overlap_saves(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9, 30), utc(2026, 7, 6, 11))
        response = self.client.post(
            reverse("entry_create"), entry_form_data(self.project, confirm_overlap="1")
        )
        self.assertRedirects(response, reverse("entry_list"))
        self.assertEqual(TimeEntry.objects.count(), 2)

    def test_no_warning_for_adjacent_entry(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 8), utc(2026, 7, 6, 9))
        response = self.client.post(reverse("entry_create"), entry_form_data(self.project))
        self.assertRedirects(response, reverse("entry_list"))
        self.assertEqual(TimeEntry.objects.count(), 2)


class EntryEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = make_user("alice")
        cls.other_member = make_user("bob")
        cls.admin = make_user("root", role="admin")
        cls.project = make_project(rate="100.00")

    def setUp(self):
        self.entry = make_entry(
            self.member, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10), rate="100.00"
        )
        self.edit_url = reverse("entry_edit", args=[self.entry.pk])

    def test_member_edits_own_entry_times(self):
        self.client.force_login(self.member)
        response = self.client.post(
            self.edit_url,
            entry_form_data(self.project, started_at="2026-07-06T08:30",
                            ended_at="2026-07-06T09:45"),
        )
        self.assertRedirects(response, reverse("entry_list"))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.started_at, utc(2026, 7, 6, 8, 30))
        self.assertEqual(self.entry.ended_at, utc(2026, 7, 6, 9, 45))

    def test_editing_does_not_warn_about_itself(self):
        self.client.force_login(self.member)
        response = self.client.post(self.edit_url, entry_form_data(self.project))
        self.assertRedirects(response, reverse("entry_list"))

    def test_edit_warns_when_overlapping_another_entry(self):
        make_entry(self.member, self.project, utc(2026, 7, 6, 9, 45), utc(2026, 7, 6, 11))
        self.client.force_login(self.member)
        response = self.client.post(self.edit_url, entry_form_data(self.project))
        self.assertContains(response, "Save anyway")

    def test_member_cannot_see_or_edit_others_entries(self):
        self.client.force_login(self.other_member)
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(
            self.client.post(self.edit_url, entry_form_data(self.project)).status_code, 404
        )

    def test_admin_edit_preserves_original_owner(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.edit_url, entry_form_data(self.project, description="Fixed by admin")
        )
        self.assertRedirects(response, reverse("entry_list"))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.user, self.member)  # not reassigned to the admin
        self.assertEqual(self.entry.description, "Fixed by admin")

    def test_running_entry_may_keep_open_end(self):
        running = make_entry(self.member, self.project, utc(2026, 7, 6, 12), None)
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("entry_edit", args=[running.pk]),
            entry_form_data(self.project, started_at="2026-07-06T11:30", ended_at=""),
        )
        self.assertRedirects(response, reverse("entry_list"))
        running.refresh_from_db()
        self.assertIsNone(running.ended_at)  # still running
        self.assertEqual(running.started_at, utc(2026, 7, 6, 11, 30))

    def test_member_deletes_own_entry(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("entry_delete", args=[self.entry.pk]))
        self.assertRedirects(response, reverse("entry_list"))
        self.assertFalse(TimeEntry.objects.filter(pk=self.entry.pk).exists())

    def test_member_cannot_delete_others_entries(self):
        self.client.force_login(self.other_member)
        response = self.client.post(reverse("entry_delete", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(TimeEntry.objects.filter(pk=self.entry.pk).exists())
