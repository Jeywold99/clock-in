from zoneinfo import available_timezones

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User

TIMEZONE_CHOICES = [(tz, tz) for tz in sorted(available_timezones())]


class MemberCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "timezone"]
        widgets = {"timezone": forms.Select(choices=TIMEZONE_CHOICES)}


class MemberEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "timezone", "is_active"]
        widgets = {"timezone": forms.Select(choices=TIMEZONE_CHOICES)}
        help_texts = {
            "is_active": "Uncheck to disable login. Their time entries are kept.",
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "timezone", "idle_threshold_hours"]
        widgets = {"timezone": forms.Select(choices=TIMEZONE_CHOICES)}
        labels = {"idle_threshold_hours": "Idle warning after (hours)"}
