from django.urls import path

from . import views

urlpatterns = [
    path("team/", views.team_list, name="team_list"),
    path("team/new/", views.team_create, name="team_create"),
    path("team/<int:pk>/edit/", views.team_edit, name="team_edit"),
    path("settings/", views.settings_view, name="settings"),
]
