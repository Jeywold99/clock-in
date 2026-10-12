from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "timezone", "is_active")
    list_filter = UserAdmin.list_filter + ("role",)
    fieldsets = UserAdmin.fieldsets + (
        ("Time tracking", {"fields": ("role", "timezone", "idle_threshold_hours")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Time tracking", {"fields": ("role", "timezone", "idle_threshold_hours")}),
    )
