"""URLs for the academics section of the site."""

from django.urls import path

from . import views


app_name = "academics"

urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("", views.dashboard, name="dashboard"),
    path("subjects/", views.subject_list, name="subjects"),
    path("subjects/new/", views.subject_create, name="subject-create"),
    path("tasks/new/", views.task_create, name="task-create"),
    path("tasks/<int:task_id>/edit/", views.task_update, name="task-update"),
    path("tasks/<int:task_id>/delete/", views.task_delete, name="task-delete"),
    path("study-sessions/new/", views.study_session_create, name="study-session-create"),
    path("assistant/", views.assistant_chat, name="assistant"),
    path("assistant/actions/<int:action_id>/approve/", views.assistant_action_approve, name="assistant-action-approve"),
    path("assistant/actions/<int:action_id>/reject/", views.assistant_action_reject, name="assistant-action-reject"),
    path("study-plan/", views.study_plan, name="study-plan"),
    path("preferences/", views.study_preferences, name="study-preferences"),
]

