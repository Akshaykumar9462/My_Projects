"""A small, explainable planner that turns pending tasks into focus blocks."""

from datetime import date

from django.utils import timezone

from academics.models import AcademicTask, StudyPreferences


DEFAULT_AVAILABLE_MINUTES = 120
DEFAULT_SESSION_MINUTES = 25
DEFAULT_BREAK_MINUTES = 5


def build_study_plan(user, today=None, available_minutes=None):
    """Suggest focus blocks within a student's available study time.

    Tasks with the nearest deadlines come first. Priority breaks ties between
    tasks with the same deadline. The function only reads data; it does not
    create or update tasks, calendar entries, or study sessions.
    """
    today = today or timezone.localdate()
    preferences = StudyPreferences.objects.filter(owner=user).first()
    session_minutes = (
        preferences.preferred_session_minutes if preferences else DEFAULT_SESSION_MINUTES
    )
    break_minutes = preferences.break_minutes if preferences else DEFAULT_BREAK_MINUTES
    daily_minutes = (
        available_minutes
        if available_minutes is not None
        else (
            preferences.daily_available_minutes
            if preferences
            else DEFAULT_AVAILABLE_MINUTES
        )
    )
    if not 0 <= daily_minutes <= 720:
        raise ValueError("Available study time must be from 0 to 720 minutes.")

    pending_tasks = list(
        AcademicTask.objects.filter(subject__owner=user)
        .exclude(status=AcademicTask.Status.COMPLETED)
        .select_related("subject")
    )
    priority_order = {
        AcademicTask.Priority.HIGH: 0,
        AcademicTask.Priority.MEDIUM: 1,
        AcademicTask.Priority.LOW: 2,
    }
    pending_tasks.sort(
        key=lambda task: (
            task.due_date is None,
            task.due_date or date.max,
            priority_order[task.priority],
            task.title.casefold(),
        )
    )

    minutes_left = daily_minutes
    focus_blocks = []
    unplanned_tasks = []
    for task in pending_tasks:
        task_minutes_left = task.estimated_minutes or session_minutes
        session_number = 1
        while task_minutes_left > 0 and minutes_left > 0:
            focus_minutes = min(session_minutes, task_minutes_left, minutes_left)
            focus_blocks.append(
                {
                    "task": task,
                    "session_number": session_number,
                    "duration_minutes": focus_minutes,
                    "break_minutes": break_minutes,
                }
            )
            task_minutes_left -= focus_minutes
            minutes_left -= focus_minutes
            session_number += 1
        if task_minutes_left > 0:
            unplanned_tasks.append(
                {
                    "task": task,
                    "remaining_minutes": task_minutes_left,
                    "estimated": task.estimated_minutes is not None,
                }
            )

    return {
        "today": today,
        "available_minutes": daily_minutes,
        "planned_minutes": daily_minutes - minutes_left,
        "remaining_available_minutes": minutes_left,
        "session_minutes": session_minutes,
        "break_minutes": break_minutes,
        "pending_count": len(pending_tasks),
        "focus_blocks": focus_blocks,
        "unplanned_tasks": unplanned_tasks,
    }

