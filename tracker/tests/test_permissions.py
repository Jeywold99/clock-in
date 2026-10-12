from django.test import TestCase
from django.urls import reverse

from .utils import make_user


class AdminOnlyPageTests(TestCase):
    ADMIN_ONLY = ["client_list", "client_create", "project_list", "project_create",
                  "team_list", "team_create"]
    EVERYONE = ["dashboard", "entry_list", "tag_list", "report_summary",
                "report_timesheet", "settings"]

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("root", role="admin")
        cls.member = make_user("alice")

    def test_members_get_403_on_admin_pages(self):
        self.client.force_login(self.member)
        for name in self.ADMIN_ONLY:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_admins_can_load_admin_pages(self):
        self.client.force_login(self.admin)
        for name in self.ADMIN_ONLY:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_members_can_load_shared_pages(self):
        self.client.force_login(self.member)
        for name in self.EVERYONE:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_anonymous_users_are_redirected_to_login(self):
        for name in self.ADMIN_ONLY + self.EVERYONE:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)


class TeamGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("root", role="admin")
        cls.member = make_user("alice")

    def edit_payload(self, **overrides):
        data = {
            "first_name": "", "last_name": "", "email": "",
            "role": "admin", "timezone": "UTC", "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_admin_cannot_demote_self(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("team_edit", args=[self.admin.pk]), self.edit_payload(role="member")
        )
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "admin")

    def test_admin_cannot_deactivate_self(self):
        self.client.force_login(self.admin)
        payload = self.edit_payload()
        del payload["is_active"]  # unchecked checkbox
        self.client.post(reverse("team_edit", args=[self.admin.pk]), payload)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_promote_and_deactivate_others(self):
        self.client.force_login(self.admin)
        payload = self.edit_payload(role="member")
        del payload["is_active"]
        self.client.post(reverse("team_edit", args=[self.member.pk]), payload)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)

    def test_weak_password_rejected_on_user_creation(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("team_create"), {
            "username": "newbie", "first_name": "", "last_name": "", "email": "",
            "role": "member", "timezone": "UTC",
            "password1": "password", "password2": "password",
        })
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        self.assertContains(response, "too common")
