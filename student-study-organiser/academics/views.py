"""Views for the dashboard and the first database-backed study workflows."""

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import AcademicTaskForm, StudyPreferencesForm, StudySessionForm, SubjectForm
from .models import (
    AcademicTask,
    ChatMessage,
    PendingAction,
    StudyConversation,
    StudyPreferences,
    Subject,
)
from .services.assistant import (
    AssistantSetupError,
    approve_pending_action,
    generate_reply,
    reject_pending_action,
)
from .services.progress import build_progress_summary
from .services.planning import build_study_plan


def _due_label(due_date, today):
    """Turn a due date into a short label that is easy to scan."""
    if due_date is None:
        return "No due date"

    days_until_due = (due_date - today).days
    if days_until_due < 0:
        days_ago = abs(days_until_due)
        return "Overdue by 1 day" if days_ago == 1 else f"Overdue by {days_ago} days"
    if days_until_due == 0:
        return "Due today"
    if days_until_due == 1:
        return "Due tomorrow"
    return f"Due in {days_until_due} days"


def health_check(request):
    """Give the hosting platform a lightweight endpoint for deploy health checks."""
    return JsonResponse({"status": "ok"})


def home(request):
    """Show public information to visitors and the private dashboard to students."""
    if request.user.is_authenticated:
        return redirect("academics:dashboard")

    return render(
        request,
        "academics/home.html",
        {"canonical_url": request.build_absolute_uri("/")},
    )


@login_required
def dashboard(request):
    """Show saved tasks and evidence-based, rule-generated progress insights."""
    today = timezone.localdate()
    summary = build_progress_summary(request.user, today=today)
    for task in summary["tasks"]:
        task.due_label = _due_label(task.due_date, today)
        task.status_class = task.status.replace("_", "-")
        task.formatted_due_date = task.due_date.strftime("%b %d") if task.due_date else "—"

    context = {
        "today_label": today.strftime("%A, %B %d"),
        "subject_count": Subject.objects.filter(owner=request.user).count(),
        **summary,
    }
    return render(request, "academics/dashboard.html", context)


@login_required
def subject_list(request):
    """Show subjects saved in the local database."""
    return render(
        request,
        "academics/subject_list.html",
        {"subjects": Subject.objects.filter(owner=request.user)},
    )


@login_required
def subject_create(request):
    """Create one subject after validating its name."""
    if request.method == "POST":
        form = SubjectForm(request.POST, user=request.user)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f"Added {subject.name}.")
            return redirect("academics:subjects")
    else:
        form = SubjectForm(user=request.user)

    return render(
        request,
        "academics/form_page.html",
        {
            "form": form,
            "page_title": "Add a subject",
            "page_description": "Create a subject before adding its assignments, exams, or projects.",
            "submit_label": "Save subject",
            "cancel_url_name": "academics:subjects",
        },
    )


@login_required
def task_create(request):
    """Create an academic task from a validated form."""
    if request.method == "POST":
        form = AcademicTaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save()
            messages.success(request, f"Added {task.title}.")
            return redirect("academics:dashboard")
    else:
        form = AcademicTaskForm(user=request.user)

    return render(
        request,
        "academics/form_page.html",
        {
            "form": form,
            "page_title": "Add an academic task",
            "page_description": "Enter the key details. You can update them later.",
            "submit_label": "Save task",
            "cancel_url_name": "academics:dashboard",
            "needs_subject": not Subject.objects.filter(owner=request.user).exists(),
        },
    )


@login_required
def task_update(request, task_id):
    """Edit an existing task while preserving validation."""
    task = get_object_or_404(
        AcademicTask.objects.filter(subject__owner=request.user), pk=task_id
    )
    if request.method == "POST":
        form = AcademicTaskForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            task = form.save()
            messages.success(request, f"Updated {task.title}.")
            return redirect("academics:dashboard")
    else:
        form = AcademicTaskForm(instance=task, user=request.user)

    return render(
        request,
        "academics/form_page.html",
        {
            "form": form,
            "page_title": "Edit task",
            "page_description": "Update the task details or status.",
            "submit_label": "Save changes",
            "cancel_url_name": "academics:dashboard",
        },
    )


@login_required
def task_delete(request, task_id):
    """Require a confirmation page and POST before deleting a task."""
    task = get_object_or_404(
        AcademicTask.objects.filter(subject__owner=request.user), pk=task_id
    )
    if request.method == "POST":
        title = task.title
        task.delete()
        messages.success(request, f"Deleted {title}.")
        return redirect("academics:dashboard")

    return render(request, "academics/confirm_delete.html", {"task": task})


@login_required
def study_session_create(request):
    """Record a completed study session."""
    if request.method == "POST":
        form = StudySessionForm(request.POST, user=request.user)
        if form.is_valid():
            session = form.save()
            messages.success(
                request,
                f"Logged {session.duration_minutes} study minutes for {session.subject.name}.",
            )
            return redirect("academics:dashboard")
    else:
        form = StudySessionForm(user=request.user)

    return render(
        request,
        "academics/form_page.html",
        {
            "form": form,
            "page_title": "Log a study session",
            "page_description": "Record study time so the progress dashboard can reflect it.",
            "submit_label": "Save study session",
            "cancel_url_name": "academics:dashboard",
            "needs_subject": not Subject.objects.filter(owner=request.user).exists(),
        },
    )


def register(request):
    """Create an account and let the first student adopt the local demo data."""
    if request.user.is_authenticated:
        return redirect("academics:dashboard")

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                legacy_user = get_user_model().objects.filter(
                    username="__local_demo_owner__"
                ).first()
                if legacy_user:
                    Subject.objects.filter(owner=legacy_user).update(owner=user)
            login(request, user)
            messages.success(request, "Your account is ready. Welcome to Study Organiser.")
            return redirect("academics:dashboard")
    else:
        form = UserCreationForm()

    return render(
        request,
        "registration/signup.html",
        {"form": form},
    )


@login_required
def assistant_chat(request):
    """Save a student's conversation and ask the assistant for a response."""
    conversation, _ = StudyConversation.objects.get_or_create(owner=request.user)
    if request.method == "POST":
        message_text = request.POST.get("message", "").strip()
        if not message_text:
            messages.error(request, "Write a question or request first.")
        elif len(message_text) > 4000:
            messages.error(request, "Please keep each message under 4,000 characters.")
        else:
            ChatMessage.objects.create(
                conversation=conversation,
                role=ChatMessage.Role.USER,
                content=message_text,
            )
            try:
                reply = generate_reply(request.user, conversation)
            except AssistantSetupError as error:
                reply = str(error)
            except Exception:
                reply = (
                    "I couldn't reach the AI service just now. Your message is saved; "
                    "please check the API setup and try again."
                )
            ChatMessage.objects.create(
                conversation=conversation,
                role=ChatMessage.Role.ASSISTANT,
                content=reply,
            )
        return redirect("academics:assistant")

    chat_messages = list(conversation.messages.order_by("-created_at", "-pk")[:40])
    chat_messages.reverse()
    return render(
        request,
        "academics/assistant.html",
        {
            "chat_messages": chat_messages,
            "pending_actions": conversation.pending_actions.filter(
                status=PendingAction.Status.PENDING
            ),
        },
    )


@login_required
def assistant_action_approve(request, action_id):
    """Apply a pending task proposal after an explicit POST confirmation."""
    if request.method != "POST":
        return redirect("academics:assistant")
    description = approve_pending_action(request.user, action_id)
    messages.success(request, description)
    return redirect("academics:assistant")


@login_required
def assistant_action_reject(request, action_id):
    """Reject a proposed task change without changing academic records."""
    if request.method != "POST":
        return redirect("academics:assistant")
    reject_pending_action(request.user, action_id)
    messages.info(request, "Proposal dismissed. Your task list was not changed.")
    return redirect("academics:assistant")


@login_required
def study_plan(request):
    """Show an explainable focus-block suggestion using saved preferences."""
    plan = build_study_plan(request.user)
    return render(request, "academics/study_plan.html", {"plan": plan})


@login_required
def study_preferences(request):
    """Let the student save availability and focus-session defaults."""
    preferences, _ = StudyPreferences.objects.get_or_create(owner=request.user)
    if request.method == "POST":
        form = StudyPreferencesForm(request.POST, instance=preferences)
        if form.is_valid():
            form.save()
            messages.success(request, "Study preferences saved.")
            return redirect("academics:study-plan")
    else:
        form = StudyPreferencesForm(instance=preferences)

    return render(
        request,
        "academics/form_page.html",
        {
            "form": form,
            "page_title": "Study preferences",
            "page_description": "Set the daily time and focus-session defaults for your study plan suggestions.",
            "submit_label": "Save preferences",
            "cancel_url_name": "academics:study-plan",
        },
    )

