from django import forms

from .models import Client, Project, Tag, TimeEntry

DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"


def active_projects():
    return Project.objects.filter(is_archived=False, client__is_archived=False).select_related("client")


class TimerStartForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none(), empty_label="Select a project…")
    description = forms.CharField(
        max_length=500, required=False,
        widget=forms.TextInput(attrs={"placeholder": "What are you working on?"}),
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(), required=False, widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = active_projects()


class TimeEntryForm(forms.ModelForm):
    started_at = forms.DateTimeField(
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT),
    )
    ended_at = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_LOCAL_FORMAT],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT),
    )

    class Meta:
        model = TimeEntry
        fields = ["project", "description", "started_at", "ended_at", "is_billable", "rate_applied", "tags"]
        widgets = {
            "description": forms.TextInput(),
            "tags": forms.CheckboxSelectMultiple(),
        }
        help_texts = {
            "rate_applied": "Hourly rate for this entry. Defaults to the project rate when left blank on a billable entry.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = active_projects()
        # Keep an archived project selectable when editing an entry that uses it.
        if self.instance.pk and self.instance.project_id:
            qs = (qs | Project.objects.filter(pk=self.instance.project_id)).distinct()
        self.fields["project"].queryset = qs

    def clean_ended_at(self):
        ended_at = self.cleaned_data.get("ended_at")
        # Only the currently running entry may keep an open end; everything
        # else must be finished (the DB allows one running entry per user).
        if ended_at is None and not (self.instance.pk and self.instance.is_running):
            raise forms.ValidationError("End time is required for a manual entry.")
        return ended_at


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "contact_email", "currency", "notes", "is_archived"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
        help_texts = {
            "currency": "ISO code (USD, EUR, …) used when showing amounts.",
            "is_archived": "Archived clients disappear from pickers but stay in reports.",
        }


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["client", "name", "hourly_rate", "is_billable_default", "is_archived"]
        help_texts = {
            "hourly_rate": "Rate changes only affect new entries — existing "
                           "entries keep the rate they were tracked at.",
            "is_archived": "Archived projects disappear from pickers but stay in reports.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Client.objects.filter(is_archived=False)
        if self.instance.pk and self.instance.client_id:
            qs = (qs | Client.objects.filter(pk=self.instance.client_id)).distinct()
        self.fields["client"].queryset = qs


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "New tag name"})}
