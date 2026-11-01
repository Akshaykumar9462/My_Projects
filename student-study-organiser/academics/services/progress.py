"""Explainable progress metrics and rule-based study suggestions."""

from datetime import date, timedelta

from django.db.models import Sum
from django.utils import timezone

from academics.models import AcademicTask, StudySession


def build_progress_summary(user, today=None):
    """Summarise saved work for this week and suggest a few next steps.

    Passing ``today`` makes the date rules deterministic in tests. In normal
    use, the date comes from Django's configured time zone.
    """
    today = today or timezone.localdate()
    tasks = list(
        AcademicTask.objects.filter(subject__owner=user).select_related("subject")
    )
    tasks.sort(
        key=lambda task: (
            task.status == AcademicTask.Status.COMPLETED,
            task.due_date is None,
            task.due_date or date.max,
            task.title.lower(),
        )
    )

    pending_tasks = [task for task in tasks if task.status != AcademicTask.Status.COMPLETED]
    overdue_tasks = [
        task for task in pending_tasks if task.due_date and task.due_date < today
    ]
    due_soon_tasks = [
        task
        for task in pending_tasks
        if task.due_date and today <= task.due_date <= today + timedelta(days=7)
    ]
    completed_count = sum(task.status == AcademicTask.Status.COMPLETED for task in tasks)
    progress_percent = round(completed_count / len(tasks) * 100) if tasks else 0

    week_start = today - timedelta(days=today.weekday())
    previous_week_start = week_start - timedelta(days=7)
    previous_week_end = week_start - timedelta(days=1)
    study_minutes_this_week = _study_minutes_between(user, week_start, today)
    study_minutes_last_week = _study_minutes_between(
        user, previous_week_start, previous_week_end
    )

    return {
        "tasks": tasks,
        "total_count": len(tasks),
        "completed_count": completed_count,
        "pending_count": len(pending_tasks),
        "progress_percent": progress_percent,
        "overdue_count": len(overdue_tasks),
        "due_soon_count": len(due_soon_tasks),
        "study_minutes_this_week": study_minutes_this_week,
        "study_minutes_last_week": study_minutes_last_week,
        "study_time_change_label": _study_time_change_label(
            study_minutes_this_week,
            study_minutes_last_week,
        ),
        "suggestions": (
            _build_suggestions(
                pending_tasks,
                overdue_tasks,
                due_soon_tasks,
                study_minutes_this_week,
                today,
            )
            if tasks
            else [
                {
                    "title": "Add your first task",
                    "message": "Create a subject and add an assignment, exam, or project to start tracking progress.",
                    "reason": "There are no saved tasks yet.",
                    "tone": "neutral",
                }
            ]
        ),
    }


def _study_minutes_between(user, start_date, end_date):
    """Add study minutes recorded between two inclusive calendar dates."""
    return (
        StudySession.objects.filter(
            study_date__gte=start_date,
            study_date__lte=end_date,
            subject__owner=user,
        ).aggregate(total=Sum("duration_minutes"))["total"]
        or 0
    )


def _study_time_change_label(this_week, last_week):
    """Describe the week-to-week change without judging the student's effort."""
    if last_week == 0:
        return "No study time logged last week"
    difference = this_week - last_week
    if difference > 0:
        return f"{difference} more minutes than last week"
    if difference < 0:
        return f"{abs(difference)} fewer minutes than last week"
    return "Same study time as last week"


def _build_suggestions(pending_tasks, overdue_tasks, due_soon_tasks, minutes_this_week, today):
    """Create short suggestions with explicit reasons from the saved records."""
    suggestions = []

    if overdue_tasks:
        earliest_overdue = min(overdue_tasks, key=lambda task: task.due_date)
        overdue_days = (today - earliest_overdue.due_date).days
        suggestions.append(
            {
                "title": "Review an overdue task",
                "message": (
                    f"{earliest_overdue.title} is {overdue_days} day(s) past its due date. "
                    "Update its status or choose a new plan for it."
                ),
                "reason": f"{len(overdue_tasks)} pending task(s) have passed their due date.",
                "tone": "attention",
            }
        )

    if due_soon_tasks:
        next_task = min(
            due_soon_tasks,
            key=lambda task: (
                task.due_date,
                task.priority != AcademicTask.Priority.HIGH,
            ),
        )
        days_until_due = (next_task.due_date - today).days
        timing = "due today" if days_until_due == 0 else f"due in {days_until_due} day(s)"
        suggestions.append(
            {
                "title": "Choose a near-term focus",
                "message": f"Consider a short session for {next_task.title}, {timing}.",
                "reason": "This task is pending and due within the next 7 days.",
                "tone": "focus",
            }
        )

    if pending_tasks and minutes_this_week == 0:
        suggestions.append(
            {
                "title": "Log your study time",
                "message": "Record a study session when you finish one to make your weekly progress more useful.",
                "reason": "No study sessions are recorded from Monday through today this week.",
                "tone": "neutral",
            }
        )

    if not suggestions and not pending_tasks:
        suggestions.append(
            {
                "title": "You are up to date",
                "message": "There are no pending tasks. Check your later deadlines when you are ready.",
                "reason": "Every saved task is marked completed.",
                "tone": "positive",
            }
        )

    if not suggestions and pending_tasks:
        suggestions.append(
            {
                "title": "Plan a steady next step",
                "message": "Nothing is due in the next week. You could make progress on a later task in a short session.",
                "reason": "Pending tasks exist, but none are due within 7 days.",
                "tone": "neutral",
            }
        )

    return suggestions

