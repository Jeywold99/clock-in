from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import MemberCreateForm, MemberEditForm, ProfileForm
from .models import User


@admin_required
def team_list(request):
    users = User.objects.annotate(entry_count=Count("time_entries")).order_by("username")
    return render(request, "accounts/team_list.html", {"users": users})


@admin_required
def team_create(request):
    if request.method == "POST":
        form = MemberCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"User {user.username} created.")
            return redirect("team_list")
    else:
        form = MemberCreateForm()
    return render(request, "accounts/team_form.html", {"form": form, "heading": "New user"})


@admin_required
def team_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = MemberEditForm(request.POST, instance=user)
        if form.is_valid():
            # Don't let an admin lock themselves out by demoting or
            # deactivating their own account.
            if user == request.user and (
                not form.cleaned_data["is_active"]
                or form.cleaned_data["role"] != User.Role.ADMIN
            ):
                messages.error(request, "You can't deactivate or demote your own account.")
            else:
                form.save()
                messages.success(request, f"User {user.username} updated.")
                return redirect("team_list")
    else:
        form = MemberEditForm(instance=user)
    return render(request, "accounts/team_form.html", {
        "form": form, "heading": f"Edit {user.username}", "editing": user,
    })


@login_required
def settings_view(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/settings.html", {"form": form})
