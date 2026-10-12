from django.contrib import admin

from .models import Client, Project, Tag, TimeEntry


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_email", "currency", "is_archived")
    list_filter = ("is_archived",)
    search_fields = ("name", "contact_email")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "hourly_rate", "is_billable_default", "is_archived")
    list_filter = ("is_archived", "client")
    search_fields = ("name", "client__name")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "started_at", "ended_at", "is_billable", "rate_applied")
    list_filter = ("is_billable", "project__client", "user")
    search_fields = ("description",)
    date_hierarchy = "started_at"
    autocomplete_fields = ("project",)
    filter_horizontal = ("tags",)
