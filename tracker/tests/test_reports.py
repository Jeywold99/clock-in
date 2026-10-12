import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .utils import make_entry, make_project, make_user, utc


class ReportTestsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("root", role="admin")
        cls.alice = make_user("alice")
        cls.bob = make_user("bob")
        cls.usd_project = make_project(client_name="Acme", name="Site", rate="100.00")
        cls.eur_project = make_project(
            client_name="Bluebird", name="Brand", rate="50.00", currency="EUR"
        )
        # alice: 2h USD billable + 1h EUR billable; bob: 1h USD non-billable
        make_entry(cls.alice, cls.usd_project, utc(2026, 7, 6, 9), utc(2026, 7, 6, 11),
                   rate="100.00", description="alice-usd")
        make_entry(cls.alice, cls.eur_project, utc(2026, 7, 7, 9), utc(2026, 7, 7, 10),
                   rate="50.00", description="alice-eur")
        make_entry(cls.bob, cls.usd_project, utc(2026, 7, 6, 12), utc(2026, 7, 6, 13),
                   billable=False, description="bob-nonbillable")

    RANGE = {"from": "2026-07-01", "to": "2026-07-31"}


class SummaryReportTests(ReportTestsBase):
    def test_admin_sees_everyone_with_per_currency_totals(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("report_summary"), self.RANGE)
        grand = response.context["grand"]
        self.assertEqual(grand["duration"], timedelta(hours=4))
        self.assertEqual(grand["billable"], timedelta(hours=3))
        self.assertEqual(grand["amounts"], {"USD": Decimal("200"), "EUR": Decimal("50")})

    def test_member_sees_only_their_own_time(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("report_summary"), self.RANGE)
        self.assertEqual(response.context["grand"]["duration"], timedelta(hours=3))

    def test_member_cannot_use_user_filter(self):
        self.client.force_login(self.bob)
        response = self.client.get(
            reverse("report_summary"), {**self.RANGE, "user": self.alice.pk}
        )
        # Filter is ignored: bob still sees exactly his one hour.
        self.assertEqual(response.context["grand"]["duration"], timedelta(hours=1))

    def test_admin_user_filter_narrows_report(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("report_summary"), {**self.RANGE, "user": self.bob.pk}
        )
        self.assertEqual(response.context["grand"]["duration"], timedelta(hours=1))
        self.assertEqual(response.context["grand"]["amounts"], {})

    def test_billable_filter(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("report_summary"), {**self.RANGE, "billable": "no"})
        self.assertEqual(response.context["grand"]["duration"], timedelta(hours=1))

    def test_running_entries_are_excluded(self):
        make_entry(self.alice, self.usd_project, utc(2026, 7, 8, 9), None)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("report_summary"), self.RANGE)
        self.assertEqual(response.context["grand"]["duration"], timedelta(hours=4))


class CsvExportTests(ReportTestsBase):
    def read_csv(self, response):
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        return list(csv.DictReader(io.StringIO(response.content.decode("utf-8"))))

    def test_export_contains_all_columns_and_rows(self):
        self.client.force_login(self.admin)
        rows = self.read_csv(self.client.get(reverse("report_export_csv"), self.RANGE))
        self.assertEqual(len(rows), 3)
        alice_usd = next(r for r in rows if r["description"] == "alice-usd")
        self.assertEqual(alice_usd["hours"], "2.00")
        self.assertEqual(alice_usd["amount"], "200.00")
        self.assertEqual(alice_usd["currency"], "USD")
        self.assertEqual(alice_usd["billable"], "yes")

    def test_nonbillable_row_has_no_amount(self):
        self.client.force_login(self.admin)
        rows = self.read_csv(self.client.get(reverse("report_export_csv"), self.RANGE))
        bob_row = next(r for r in rows if r["description"] == "bob-nonbillable")
        self.assertEqual(bob_row["amount"], "")
        self.assertEqual(bob_row["billable"], "no")

    def test_member_export_is_scoped_to_self(self):
        self.client.force_login(self.bob)
        rows = self.read_csv(self.client.get(reverse("report_export_csv"), self.RANGE))
        self.assertEqual([r["user"] for r in rows], ["bob"])

    def test_filename_reflects_range(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("report_export_csv"), self.RANGE)
        self.assertIn("2026-07-01_2026-07-31", response["Content-Disposition"])
