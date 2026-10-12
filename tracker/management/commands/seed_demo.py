"""Seed the database with demo users, clients, projects, and time entries.

Idempotent: running it twice won't duplicate data. Intended for demos and
local development, not production.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracker.models import Client, Project, Tag, TimeEntry

User = get_user_model()

DEMO_PASSWORD = "demo-pass-1234"

USERS = [
    # username, first, last, role, timezone
    ("ana", "Ana", "Reyes", User.Role.ADMIN, "Asia/Manila"),
    ("ben", "Ben", "Carter", User.Role.MEMBER, "America/New_York"),
    ("mia", "Mia", "Novak", User.Role.MEMBER, "Europe/Berlin"),
]

CLIENTS = {
    "Acme Corp": {
        "currency": "USD",
        "projects": [("Website redesign", Decimal("95.00")), ("SEO retainer", Decimal("80.00"))],
    },
    "Bluebird Studio": {
        "currency": "EUR",
        "projects": [("Brand refresh", Decimal("110.00")), ("Packaging design", Decimal("100.00"))],
    },
    "Internal": {
        "currency": "USD",
        "projects": [("Admin & ops", None), ("Marketing", None)],
    },
}

TAGS = ["design", "development", "meeting", "research", "writing", "review"]

DESCRIPTIONS = [
    "Wireframes for landing page",
    "Client kickoff call",
    "Implement responsive nav",
    "Keyword research",
    "Logo iterations",
    "Sprint planning",
    "Copy review",
    "Bug fixes from QA pass",
    "Moodboard exploration",
    "Analytics report",
]


class Command(BaseCommand):
    help = "Seed demo users, clients, projects, tags, and ~3 weeks of time entries."

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(42)  # deterministic demo data

        users = []
        for username, first, last, role, tz in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@example.com",
                    "role": role,
                    "timezone": tz,
                    "is_staff": role == User.Role.ADMIN,
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            users.append(user)

        tags = {name: Tag.objects.get_or_create(name=name)[0] for name in TAGS}

        projects = []
        for client_name, spec in CLIENTS.items():
            client, _ = Client.objects.get_or_create(
                name=client_name, defaults={"currency": spec["currency"]}
            )
            for proj_name, rate in spec["projects"]:
                project, _ = Project.objects.get_or_create(
                    client=client,
                    name=proj_name,
                    defaults={
                        "hourly_rate": rate,
                        "is_billable_default": rate is not None,
                    },
                )
                projects.append(project)

        if TimeEntry.objects.exists():
            self.stdout.write("Time entries already exist; skipping entry seeding.")
        else:
            self._seed_entries(rng, users, projects, tags)

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready. Log in as ana (admin), ben, or mia "
            f"with password: {DEMO_PASSWORD}"
        ))

    def _seed_entries(self, rng, users, projects, tags):
        tag_list = list(tags.values())
        now = timezone.now()
        count = 0
        for user in users:
            for day_offset in range(21, 0, -1):
                day = now - timedelta(days=day_offset)
                if day.weekday() >= 5 and rng.random() < 0.8:
                    continue  # mostly weekdays
                cursor = day.replace(hour=9, minute=0, second=0, microsecond=0)
                for _ in range(rng.randint(2, 4)):
                    project = rng.choice(projects)
                    duration = timedelta(minutes=rng.choice([30, 45, 60, 90, 120, 150]))
                    entry = TimeEntry.objects.create(
                        user=user,
                        project=project,
                        description=rng.choice(DESCRIPTIONS),
                        started_at=cursor,
                        ended_at=cursor + duration,
                        is_billable=project.is_billable_default,
                        rate_applied=project.hourly_rate,
                    )
                    entry.tags.set(rng.sample(tag_list, rng.randint(0, 2)))
                    gap = timedelta(minutes=rng.choice([0, 15, 30, 60]))
                    cursor += duration + gap
                    count += 1
        self.stdout.write(f"Created {count} time entries.")
