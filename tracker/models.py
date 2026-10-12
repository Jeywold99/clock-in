from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(TimestampedModel):
    name = models.CharField(max_length=200)
    contact_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    # Currency lives on the client so future invoices inherit it.
    currency = models.CharField(max_length=3, default="USD")
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_client_name_ci",
                violation_error_message="A client with this name already exists.",
            ),
        ]

    def __str__(self):
        return self.name


class Project(TimestampedModel):
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="projects")
    name = models.CharField(max_length=200)
    hourly_rate = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text="Leave blank for projects that are never billed.",
    )
    is_billable_default = models.BooleanField(
        default=True, help_text="New entries on this project start as billable.",
    )
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["client__name", "name"]
        constraints = [
            models.UniqueConstraint(
                "client",
                Lower("name"),
                name="unique_project_name_per_client_ci",
                violation_error_message="This client already has a project with this name.",
            ),
        ]

    def __str__(self):
        return f"{self.client.name} / {self.name}"


class Tag(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_tag_name_ci",
                violation_error_message="A tag with this name already exists.",
            ),
        ]

    def __str__(self):
        return self.name


class TimeEntryQuerySet(models.QuerySet):
    def running(self):
        return self.filter(ended_at__isnull=True)

    def finished(self):
        return self.filter(ended_at__isnull=False)

    def for_user(self, user):
        """Role scoping: admins see everything, members see their own."""
        return self if user.is_admin else self.filter(user=user)

    def overlapping(self, user, started_at, ended_at, exclude_pk=None):
        """Finished entries of `user` that overlap [started_at, ended_at).

        A still-running timer counts as overlapping if it started before
        `ended_at` (its open end reaches into the candidate range).
        """
        qs = self.filter(user=user, started_at__lt=ended_at).filter(
            Q(ended_at__gt=started_at) | Q(ended_at__isnull=True)
        )
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs


class TimeEntry(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="time_entries"
    )
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="time_entries")
    description = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)  # NULL = timer running
    is_billable = models.BooleanField(default=True)
    # Snapshot of the project rate when the entry was made, so later rate
    # changes (and future invoicing) don't rewrite history. Editable.
    rate_applied = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="time_entries")

    objects = TimeEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        verbose_name_plural = "time entries"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(ended_at__isnull=True),
                name="one_running_timer_per_user",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gt=F("started_at")),
                name="entry_ends_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "started_at"]),
            models.Index(fields=["project", "started_at"]),
        ]

    def __str__(self):
        state = "running" if self.is_running else self.ended_at.isoformat()
        return f"{self.user} on {self.project} ({self.started_at.isoformat()} – {state})"

    @property
    def is_running(self):
        return self.ended_at is None

    @property
    def duration(self):
        """Timedelta; live value while the timer is running."""
        end = self.ended_at or timezone.now()
        return end - self.started_at

    @property
    def duration_hours(self):
        return self.duration.total_seconds() / 3600

    @property
    def amount(self):
        """Billable value, or None when not billable / no rate set."""
        if not self.is_billable or self.rate_applied is None or self.is_running:
            return None
        seconds = int(self.duration.total_seconds())
        return self.rate_applied * seconds / 3600

    def clean(self):
        if self.ended_at is not None and self.started_at is not None:
            if self.ended_at <= self.started_at:
                raise ValidationError({"ended_at": "End time must be after start time."})

    def overlapping_entries(self):
        """Other entries of the same user that overlap this one.

        Overlaps are allowed (freelancers sometimes double-book on purpose);
        callers surface this as a warning, never a hard error.
        """
        if self.started_at is None:
            return TimeEntry.objects.none()
        end = self.ended_at or timezone.now()
        return TimeEntry.objects.overlapping(
            self.user, self.started_at, end, exclude_pk=self.pk
        )
