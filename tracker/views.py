import csv
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, DurationField, ExpressionWrapper, F, Sum
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import admin_required

from .forms import ClientForm, ProjectForm, TagForm, TimeEntryForm, TimerStartForm
from .models import Client, Project, Tag, TimeEntry


def _running_entry(user):
    return (
        TimeEntry.objects.running()
        .filter(user=user)
        .select_related("project", "project__client")
        .first()
    )


def _base_entries(user):
    return (
        TimeEntry.objects.for_user(user)
        .select_related("project", "project__client", "user")
        .prefetch_related("tags")
    )


@login_required
def dashboard(request):
    running = _running_entry(request.user)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())

    today_entries = (
        _base_entries(request.user)
        .filter(user=request.user, started_at__date=today)
        .order_by("-started_at")
    )
    duration_expr = ExpressionWrapper(
        F("ended_at") - F("started_at"), output_field=DurationField()
    )
    week_total = (
        TimeEntry.objects.finished()
        .filter(user=request.user, started_at__date__gte=week_start)
        .aggregate(total=Sum(duration_expr))["total"]
    ) or timedelta()

    idle_threshold = timedelta(hours=float(request.user.idle_threshold_hours))
    context = {
        "running": running,
        "start_form": TimerStartForm(),
        "today_entries": today_entries,
        "week_total": week_total,
        "idle_threshold_seconds": int(idle_threshold.total_seconds()),
        "is_idle": bool(running and running.duration > idle_threshold),
    }
    return render(request, "tracker/dashboard.html", context)


@login_required
def timer_start(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = TimerStartForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Couldn't start the timer — pick a project.")
        return redirect("dashboard")
    project = form.cleaned_data["project"]
    try:
        with transaction.atomic():
            entry = TimeEntry.objects.create(
                user=request.user,
                project=project,
                description=form.cleaned_data["description"],
                started_at=timezone.now(),
                is_billable=project.is_billable_default,
                rate_applied=project.hourly_rate,
            )
            entry.tags.set(form.cleaned_data["tags"])
    except IntegrityError:
        # Partial unique index: a timer is already running (e.g. second tab).
        messages.warning(request, "You already have a timer running.")
    else:
        messages.success(request, f"Timer started on {project}.")
    return redirect("dashboard")


@login_required
def timer_stop(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    running = _running_entry(request.user)
    if running is None:
        messages.warning(request, "No timer is running.")
        return redirect("dashboard")
    # Clamp so an instant stop can't violate the ended_at > started_at constraint.
    running.ended_at = max(timezone.now(), running.started_at + timedelta(seconds=1))
    running.save(update_fields=["ended_at", "updated_at"])
    hours, rem = divmod(int(running.duration.total_seconds()), 3600)
    messages.success(
        request,
        f"Stopped timer on {running.project} at {hours}:{rem // 60:02d} — "
        "you can edit the times if needed.",
    )
    return redirect("dashboard")


@login_required
def timer_discard(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    running = _running_entry(request.user)
    if running is None:
        messages.warning(request, "No timer is running.")
    else:
        running.delete()
        messages.success(request, "Timer discarded — nothing was recorded.")
    return redirect("dashboard")


def _parse_date(value, default):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def _apply_entry_filters(request, entries):
    """Apply the shared GET filters (dates, project, client, billable, and —
    for admins — user) used by the entries list, reports, and CSV export."""
    filters = {
        "from": request.GET.get("from") or "",
        "to": request.GET.get("to") or "",
        "client": request.GET.get("client") or "",
        "project": request.GET.get("project") or "",
        "billable": request.GET.get("billable") or "",
        "user": request.GET.get("user") or "",
    }
    date_from = _parse_date(filters["from"], None)
    date_to = _parse_date(filters["to"], None)
    if date_from:
        entries = entries.filter(started_at__date__gte=date_from)
    if date_to:
        entries = entries.filter(started_at__date__lte=date_to)
    if filters["client"]:
        entries = entries.filter(project__client_id=filters["client"])
    if filters["project"]:
        entries = entries.filter(project_id=filters["project"])
    if filters["billable"] in ("yes", "no"):
        entries = entries.filter(is_billable=(filters["billable"] == "yes"))
    if filters["user"] and request.user.is_admin:
        entries = entries.filter(user_id=filters["user"])
    return entries, filters


def _team_members():
    return get_user_model().objects.filter(is_active=True).order_by("username")


@login_required
def entry_list(request):
    entries, filters = _apply_entry_filters(
        request, _base_entries(request.user).order_by("-started_at")
    )

    projects = Project.objects.select_related("client").order_by("client__name", "name")
    paginator = Paginator(entries, 50)
    page = paginator.get_page(request.GET.get("page"))

    # Preserve filters across pagination links.
    params = request.GET.copy()
    params.pop("page", None)

    return render(request, "tracker/entry_list.html", {
        "page": page,
        "projects": projects,
        "team": _team_members() if request.user.is_admin else None,
        "filters": filters,
        "querystring": params.urlencode(),
    })


def _save_entry_with_overlap_check(request, form, entry_user, template, context):
    """Shared create/edit flow: warn about overlaps unless already confirmed."""
    entry = form.save(commit=False)
    entry.user = entry_user
    if entry.is_billable and entry.rate_applied is None:
        entry.rate_applied = entry.project.hourly_rate

    overlaps = entry.overlapping_entries().select_related("project", "project__client")
    if overlaps.exists() and not request.POST.get("confirm_overlap"):
        context.update({"form": form, "overlaps": overlaps, "show_overlap_confirm": True})
        return render(request, template, context)

    entry.save()
    form.save_m2m()
    return None


@login_required
def entry_create(request):
    context = {"heading": "New time entry"}
    if request.method == "POST":
        form = TimeEntryForm(request.POST)
        if form.is_valid():
            response = _save_entry_with_overlap_check(
                request, form, request.user, "tracker/entry_form.html", context
            )
            if response is not None:
                return response
            messages.success(request, "Entry added.")
            return redirect("entry_list")
    else:
        now = timezone.localtime().replace(second=0, microsecond=0)
        form = TimeEntryForm(initial={"started_at": now - timedelta(hours=1), "ended_at": now})
    context["form"] = form
    return render(request, "tracker/entry_form.html", context)


@login_required
def entry_edit(request, pk):
    entry = get_object_or_404(TimeEntry.objects.for_user(request.user), pk=pk)
    context = {"heading": "Edit time entry", "entry": entry}
    if request.method == "POST":
        form = TimeEntryForm(request.POST, instance=entry)
        if form.is_valid():
            response = _save_entry_with_overlap_check(
                request, form, entry.user, "tracker/entry_form.html", context
            )
            if response is not None:
                return response
            messages.success(request, "Entry updated.")
            return redirect("entry_list")
    else:
        form = TimeEntryForm(instance=entry)
    context["form"] = form
    return render(request, "tracker/entry_form.html", context)


@login_required
def entry_delete(request, pk):
    entry = get_object_or_404(TimeEntry.objects.for_user(request.user), pk=pk)
    if request.method == "POST":
        entry.delete()
        messages.success(request, "Entry deleted.")
        return redirect("entry_list")
    return render(request, "tracker/entry_confirm_delete.html", {"entry": entry})


# --- Reports ---


def _report_entries(request):
    """Finished entries within the requested filters, defaulting the date
    range to the current month. Returns (entries, filters)."""
    today = timezone.localdate()
    if not request.GET.get("from"):
        request.GET = request.GET.copy()
        request.GET["from"] = today.replace(day=1).isoformat()
        request.GET.setdefault("to", today.isoformat())
    entries = (
        TimeEntry.objects.finished()
        .for_user(request.user)
        .select_related("project", "project__client", "user")
    )
    return _apply_entry_filters(request, entries)


@login_required
def report_summary(request):
    entries, filters = _report_entries(request)

    clients = {}
    grand = {"duration": timedelta(), "billable": timedelta(), "amounts": {}}
    for entry in entries:
        duration = entry.ended_at - entry.started_at
        client = entry.project.client
        c_row = clients.setdefault(client.pk, {
            "client": client,
            "duration": timedelta(), "billable": timedelta(), "amount": Decimal(0),
            "projects": {},
        })
        p_row = c_row["projects"].setdefault(entry.project_id, {
            "project": entry.project,
            "duration": timedelta(), "billable": timedelta(), "amount": Decimal(0),
        })
        for row in (c_row, p_row):
            row["duration"] += duration
        grand["duration"] += duration
        if entry.is_billable:
            for row in (c_row, p_row):
                row["billable"] += duration
            grand["billable"] += duration
            amount = entry.amount
            if amount is not None:
                c_row["amount"] += amount
                p_row["amount"] += amount
                grand["amounts"][client.currency] = (
                    grand["amounts"].get(client.currency, Decimal(0)) + amount
                )

    client_rows = sorted(clients.values(), key=lambda r: r["client"].name.lower())
    for row in client_rows:
        row["project_rows"] = sorted(
            row["projects"].values(), key=lambda r: r["project"].name.lower()
        )

    return render(request, "tracker/report_summary.html", {
        "client_rows": client_rows,
        "grand": grand,
        "grand_amounts": sorted(grand["amounts"].items()),
        "nonbillable": grand["duration"] - grand["billable"],
        "filters": filters,
        "clients": Client.objects.order_by("name"),
        "projects": Project.objects.select_related("client").order_by("client__name", "name"),
        "team": _team_members() if request.user.is_admin else None,
        "querystring": request.GET.urlencode(),
    })


@login_required
def report_timesheet(request):
    today = timezone.localdate()
    week_start = _parse_date(request.GET.get("week"), None)
    if week_start is None:
        week_start = today - timedelta(days=today.weekday())
    week_start -= timedelta(days=week_start.weekday())  # normalize to Monday
    days = [week_start + timedelta(days=i) for i in range(7)]

    subject = request.user
    if request.user.is_admin and request.GET.get("user"):
        subject = get_object_or_404(get_user_model(), pk=request.GET["user"])

    entries = (
        TimeEntry.objects.finished()
        .filter(
            user=subject,
            started_at__date__gte=week_start,
            started_at__date__lte=days[-1],
        )
        .select_related("project", "project__client")
    )

    grid = {}
    day_totals = {d: timedelta() for d in days}
    for entry in entries:
        local_day = timezone.localtime(entry.started_at).date()
        duration = entry.ended_at - entry.started_at
        row = grid.setdefault(entry.project_id, {
            "project": entry.project,
            "days": {d: timedelta() for d in days},
            "total": timedelta(),
        })
        row["days"][local_day] += duration
        row["total"] += duration
        day_totals[local_day] += duration

    rows = sorted(grid.values(), key=lambda r: str(r["project"]).lower())
    for row in rows:
        row["cells"] = [
            {"day": d, "duration": row["days"][d]} for d in days
        ]

    return render(request, "tracker/report_timesheet.html", {
        "subject": subject,
        "days": days,
        "rows": rows,
        "day_totals": [day_totals[d] for d in days],
        "week_total": sum(day_totals.values(), timedelta()),
        "week_start": week_start,
        "prev_week": week_start - timedelta(days=7),
        "next_week": week_start + timedelta(days=7),
        "team": _team_members() if request.user.is_admin else None,
    })


@login_required
def report_export_csv(request):
    entries, filters = _report_entries(request)
    entries = entries.prefetch_related("tags").order_by("started_at")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"time-entries_{filters['from']}_{filters['to']}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        "date", "user", "client", "project", "description", "tags",
        "start", "end", "hours", "billable", "rate", "amount", "currency",
    ])
    for entry in entries:
        start = timezone.localtime(entry.started_at)
        end = timezone.localtime(entry.ended_at)
        hours = Decimal(int(entry.duration.total_seconds())) / 3600
        writer.writerow([
            start.date().isoformat(),
            entry.user.username,
            entry.project.client.name,
            entry.project.name,
            entry.description,
            ", ".join(t.name for t in entry.tags.all()),
            start.strftime("%Y-%m-%d %H:%M"),
            end.strftime("%Y-%m-%d %H:%M"),
            f"{hours:.2f}",
            "yes" if entry.is_billable else "no",
            entry.rate_applied if entry.rate_applied is not None else "",
            f"{entry.amount:.2f}" if entry.amount is not None else "",
            entry.project.client.currency,
        ])
    return response


# --- Clients & projects (admin-only management, archive instead of delete) ---


@admin_required
def client_list(request):
    show_archived = request.GET.get("archived") == "1"
    clients = Client.objects.prefetch_related("projects")
    if not show_archived:
        clients = clients.filter(is_archived=False)
    return render(request, "tracker/client_list.html", {
        "clients": clients, "show_archived": show_archived,
    })


@admin_required
def client_create(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client {client.name} created.")
        return redirect("client_list")
    return render(request, "tracker/simple_form.html", {
        "form": form, "heading": "New client", "back": "client_list",
    })


@admin_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Client {client.name} updated.")
        return redirect("client_list")
    return render(request, "tracker/simple_form.html", {
        "form": form, "heading": f"Edit {client.name}", "back": "client_list",
    })


@admin_required
def project_list(request):
    show_archived = request.GET.get("archived") == "1"
    projects = Project.objects.select_related("client")
    if not show_archived:
        projects = projects.filter(is_archived=False)
    return render(request, "tracker/project_list.html", {
        "projects": projects, "show_archived": show_archived,
    })


@admin_required
def project_create(request):
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, f"Project {project.name} created.")
        return redirect("project_list")
    return render(request, "tracker/simple_form.html", {
        "form": form, "heading": "New project", "back": "project_list",
    })


@admin_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Project {project.name} updated.")
        return redirect("project_list")
    return render(request, "tracker/simple_form.html", {
        "form": form, "heading": f"Edit {project.name}", "back": "project_list",
    })


# --- Tags (any user may manage; deleting a tag just untags entries) ---


@login_required
def tag_list(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            form = TagForm(request.POST)
            if form.is_valid():
                tag = form.save()
                messages.success(request, f"Tag “{tag.name}” added.")
                return redirect("tag_list")
        elif action == "rename":
            tag = get_object_or_404(Tag, pk=request.POST.get("tag_id"))
            form = TagForm(request.POST, instance=tag)
            if form.is_valid():
                form.save()
                messages.success(request, "Tag renamed.")
                return redirect("tag_list")
        elif action == "delete":
            tag = get_object_or_404(Tag, pk=request.POST.get("tag_id"))
            name = tag.name
            tag.delete()
            messages.success(request, f"Tag “{name}” deleted and removed from entries.")
            return redirect("tag_list")
        else:
            form = TagForm()
    else:
        form = TagForm()
    tags = Tag.objects.annotate(entry_count=Count("time_entries"))
    return render(request, "tracker/tag_list.html", {"tags": tags, "form": form})
