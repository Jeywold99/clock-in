from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from tracker.models import TimeEntry

from .utils import make_entry, make_project, make_user, utc


class OverlapDetectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("alice")
        cls.other = make_user("bob")
        cls.project = make_project()

    def overlapping(self, start, end, exclude_pk=None):
        return TimeEntry.objects.overlapping(self.user, start, end, exclude_pk=exclude_pk)

    def test_adjacent_entries_do_not_overlap(self):
        # [9:00, 10:00) and [10:00, 11:00) share only a boundary instant.
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        self.assertFalse(self.overlapping(utc(2026, 7, 6, 10), utc(2026, 7, 6, 11)).exists())

    def test_partial_overlap_detected(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        self.assertTrue(self.overlapping(utc(2026, 7, 6, 9, 30), utc(2026, 7, 6, 11)).exists())

    def test_contained_entry_detected(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 12))
        self.assertTrue(self.overlapping(utc(2026, 7, 6, 10), utc(2026, 7, 6, 11)).exists())

    def test_surrounding_entry_detected(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 10), utc(2026, 7, 6, 11))
        self.assertTrue(self.overlapping(utc(2026, 7, 6, 9), utc(2026, 7, 6, 12)).exists())

    def test_other_users_entries_ignored(self):
        make_entry(self.other, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        self.assertFalse(self.overlapping(utc(2026, 7, 6, 9), utc(2026, 7, 6, 10)).exists())

    def test_running_timer_reaching_into_range_detected(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), None)
        self.assertTrue(self.overlapping(utc(2026, 7, 6, 10), utc(2026, 7, 6, 11)).exists())

    def test_running_timer_starting_after_range_ignored(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 12), None)
        self.assertFalse(self.overlapping(utc(2026, 7, 6, 10), utc(2026, 7, 6, 11)).exists())

    def test_exclude_pk_skips_the_entry_being_edited(self):
        entry = make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        self.assertFalse(
            self.overlapping(utc(2026, 7, 6, 9), utc(2026, 7, 6, 10), exclude_pk=entry.pk).exists()
        )

    def test_overlapping_entries_helper_excludes_self(self):
        entry = make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        self.assertQuerySetEqual(entry.overlapping_entries(), [])


class ConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("alice")
        cls.project = make_project()

    def test_only_one_running_timer_per_user(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_entry(self.user, self.project, utc(2026, 7, 6, 10), None)

    def test_two_users_may_both_have_running_timers(self):
        other = make_user("bob")
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), None)
        make_entry(other, self.project, utc(2026, 7, 6, 9), None)
        self.assertEqual(TimeEntry.objects.running().count(), 2)

    def test_finished_entry_frees_the_running_slot(self):
        make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        make_entry(self.user, self.project, utc(2026, 7, 6, 11), None)  # no error

    def test_end_must_be_after_start(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_entry(self.user, self.project, utc(2026, 7, 6, 10), utc(2026, 7, 6, 10))


class AmountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("alice")
        cls.project = make_project(rate="90.00")

    def test_amount_is_rate_times_hours(self):
        entry = make_entry(
            self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10, 30), rate="90.00"
        )
        self.assertEqual(entry.amount, Decimal("135"))

    def test_amount_none_without_rate(self):
        entry = make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10))
        self.assertIsNone(entry.amount)

    def test_amount_none_when_not_billable(self):
        entry = make_entry(
            self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 10),
            billable=False, rate="90.00",
        )
        self.assertIsNone(entry.amount)

    def test_amount_none_while_running(self):
        entry = make_entry(self.user, self.project, utc(2026, 7, 6, 9), None, rate="90.00")
        self.assertIsNone(entry.amount)

    def test_duration_of_finished_entry(self):
        entry = make_entry(self.user, self.project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 11, 15))
        self.assertEqual(entry.duration, timedelta(hours=2, minutes=15))
