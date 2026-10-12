from decimal import Decimal
from zoneinfo import available_timezones

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

# Computed once at import; used to validate the timezone field.
VALID_TIMEZONES = available_timezones()


def validate_timezone(value):
    if value not in VALID_TIMEZONES:
        raise ValidationError("%(value)s is not a valid IANA timezone.", params={"value": value})


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    timezone = models.CharField(
        max_length=64, default="UTC", validators=[validate_timezone],
        help_text="Times are entered and displayed in this timezone.",
    )
    idle_threshold_hours = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("4.0"),
        validators=[MinValueValidator(Decimal("0.5"))],
        help_text="Warn when a timer has been running longer than this many hours.",
    )

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN
