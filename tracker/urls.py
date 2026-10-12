from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("timer/start/", views.timer_start, name="timer_start"),
    path("timer/stop/", views.timer_stop, name="timer_stop"),
    path("timer/discard/", views.timer_discard, name="timer_discard"),
    path("entries/", views.entry_list, name="entry_list"),
    path("entries/new/", views.entry_create, name="entry_create"),
    path("entries/<int:pk>/edit/", views.entry_edit, name="entry_edit"),
    path("entries/<int:pk>/delete/", views.entry_delete, name="entry_delete"),
    path("clients/", views.client_list, name="client_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:pk>/edit/", views.client_edit, name="client_edit"),
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("tags/", views.tag_list, name="tag_list"),
    path("reports/", views.report_summary, name="report_summary"),
    path("reports/timesheet/", views.report_timesheet, name="report_timesheet"),
    path("reports/export.csv", views.report_export_csv, name="report_export_csv"),
]
