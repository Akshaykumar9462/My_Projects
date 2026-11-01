"""OpenAI conversation orchestration and student-approved task tools."""

import json
from datetime import date

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from academics.models import AcademicTask, ChatMessage, PendingAction, Subject, StudyConversation
from academics.services.progress import build_progress_summary


ASSISTANT_INSTRUCTIONS = """
You are a patient study organiser for a student. Explain things simply and be encouraging.
Use tools when you need facts about the student's saved subjects, tasks, or progress.
When asked to create or change a task, use the proposal tools. A proposal is not complete
until the student approves it in the app. Never claim a change has been saved merely
because you proposed it. Do not invent subjects, deadlines, task details, or progress.
Ask a brief follow-up question when a required detail is missing or unclear.
""".strip()


TOOLS = [
    {
        "type": "function",
        "name": "list_subjects",
        "description": "List the signed-in student's saved subjects.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "list_tasks",
        "description": "List the signed-in student's tasks and their progress status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_progress",
        "description": "Get saved progress totals, deadlines, and study-minute comparisons.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_create_task",
        "description": "Prepare a new task for the student to review and approve.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "subject_name": {"type": "string"},
                "task_type": {
                    "type": "string",
                    "enum": ["assignment", "exam", "project"],
                },
                "due_date": {"type": ["string", "null"]},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
                "estimated_minutes": {"type": ["integer", "null"]},
                "details": {"type": "string"},
            },
            "required": [
                "title",
                "subject_name",
                "task_type",
                "due_date",
                "priority",
                "estimated_minutes",
                "details",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_update_task",
        "description": "Prepare one task field change for the student to review and approve.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "field": {
                    "type": "string",
                    "enum": ["title", "due_date", "priority", "status", "estimated_minutes"],
                },
                "value": {"type": "string"},
            },
            "required": ["task_id", "field", "value"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class AssistantSetupError(Exception):
    """Explain missing local configuration without exposing credentials."""


def _create_client():
    """Load the optional SDK only when a real assistant request is made."""
    if not settings.OPENAI_API_KEY:
        raise AssistantSetupError(
            "The assistant is not connected yet. Set OPENAI_API_KEY in your environment, "
            "then restart the development server."
        )
    try:
        from openai import OpenAI
    except ImportError as error:
        raise AssistantSetupError(
            "The OpenAI SDK is not installed. Install the packages listed in requirements.txt."
        ) from error
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_reply(user, conversation, client=None):
    """Send recent chat context to OpenAI and safely handle requested tools."""
    client = client or _create_client()
    recent_messages = list(conversation.messages.order_by("-created_at", "-pk")[:12])
    recent_messages.reverse()
    input_items = [{"role": message.role, "content": message.content} for message in recent_messages]

    for _ in range(3):
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            instructions=(
                f"{ASSISTANT_INSTRUCTIONS}\n"
                f"Today's local date is {timezone.localdate().isoformat()}. "
                "Use it to interpret relative deadline phrases."
            ),
            tools=TOOLS,
            input=input_items,
        )
        function_calls = [item for item in response.output if _read(item, "type") == "function_call"]
        if not function_calls:
            return response.output_text or "I couldn't form a response. Please try rephrasing that."

        # The API needs the model's function-call items before tool results.
        input_items.extend(response.output)
        for function_call in function_calls:
            name = _read(function_call, "name")
            call_id = _read(function_call, "call_id")
            try:
                arguments = json.loads(_read(function_call, "arguments") or "{}")
                result = _run_tool(user, conversation, name, arguments)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                result = {"error": str(error)}
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                }
            )

    return "I prepared any requested task changes for your review. Please check the pending proposals below."


def _read(item, key):
    """Read a field from either an SDK object or a simple test dictionary."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _run_tool(user, conversation, name, arguments):
    """Dispatch only the small, explicit set of application tools."""
    if name == "list_subjects":
        return {"subjects": list(Subject.objects.filter(owner=user).values_list("name", flat=True))}

    if name == "list_tasks":
        tasks = AcademicTask.objects.filter(subject__owner=user).select_related("subject")[:30]
        return {
            "tasks": [
                {
                    "id": task.pk,
                    "title": task.title,
                    "subject": task.subject.name,
                    "type": task.get_task_type_display(),
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "priority": task.priority,
                    "status": task.status,
                    "estimated_minutes": task.estimated_minutes,
                }
                for task in tasks
            ]
        }

    if name == "get_progress":
        summary = build_progress_summary(user)
        return {
            "total_tasks": summary["total_count"],
            "completed_tasks": summary["completed_count"],
            "pending_tasks": summary["pending_count"],
            "overdue_tasks": summary["overdue_count"],
            "due_in_next_seven_days": summary["due_soon_count"],
            "study_minutes_this_week": summary["study_minutes_this_week"],
            "study_minutes_last_week": summary["study_minutes_last_week"],
            "suggestions": summary["suggestions"],
        }

    if name == "propose_create_task":
        return _propose_create_task(user, conversation, arguments)

    if name == "propose_update_task":
        return _propose_update_task(user, conversation, arguments)

    return {"error": "That tool is not available."}


def _propose_create_task(user, conversation, arguments):
    title = str(arguments["title"]).strip()
    subject_name = str(arguments["subject_name"]).strip()
    if not title or len(title) > 120:
        raise ValueError("Task title must contain 1 to 120 characters.")
    subject = Subject.objects.filter(owner=user, name__iexact=subject_name).first()
    if subject is None:
        raise ValueError(f"No subject named '{subject_name}' is saved on this account.")

    task_type = arguments["task_type"]
    if task_type not in AcademicTask.TaskType.values:
        raise ValueError("Choose assignment, exam, or project as the task type.")
    priority = arguments["priority"]
    if priority not in AcademicTask.Priority.values:
        raise ValueError("Choose low, medium, or high as the priority.")
    due_date = date.fromisoformat(arguments["due_date"]) if arguments["due_date"] else None
    estimated_minutes = arguments["estimated_minutes"]
    if estimated_minutes is not None and not 1 <= estimated_minutes <= 1440:
        raise ValueError("Estimated minutes must be between 1 and 1440.")

    payload = {
        "subject_id": subject.pk,
        "subject_name": subject.name,
        "title": title,
        "task_type": task_type,
        "due_date": due_date.isoformat() if due_date else None,
        "priority": priority,
        "estimated_minutes": estimated_minutes,
        "details": str(arguments["details"]).strip()[:4000],
    }
    action = PendingAction.objects.create(
        owner=user,
        conversation=conversation,
        action_type=PendingAction.ActionType.CREATE_TASK,
        payload=payload,
    )
    return {"proposal_id": action.pk, "status": "awaiting_student_approval", "task": payload}


def _propose_update_task(user, conversation, arguments):
    task_id = int(arguments["task_id"])
    task = AcademicTask.objects.filter(pk=task_id, subject__owner=user).first()
    if task is None:
        raise ValueError("That task is not available in the signed-in account.")
    field = arguments["field"]
    allowed_fields = {"title", "due_date", "priority", "status", "estimated_minutes"}
    if field not in allowed_fields:
        raise ValueError("That task field cannot be updated by the assistant.")
    value = str(arguments["value"]).strip()
    if field == "title":
        if not value or len(value) > 120:
            raise ValueError("Task title must contain 1 to 120 characters.")
    elif field == "due_date":
        value = None if value.lower() in {"none", "clear"} else date.fromisoformat(value).isoformat()
    elif field == "priority" and value not in AcademicTask.Priority.values:
        raise ValueError("Choose low, medium, or high as the priority.")
    elif field == "status" and value not in AcademicTask.Status.values:
        raise ValueError("Choose not_started, in_progress, or completed as the status.")
    elif field == "estimated_minutes":
        value = int(value)
        if not 1 <= value <= 1440:
            raise ValueError("Estimated minutes must be between 1 and 1440.")

    payload = {"task_id": task.pk, "field": field, "value": value}
    action = PendingAction.objects.create(
        owner=user,
        conversation=conversation,
        action_type=PendingAction.ActionType.UPDATE_TASK,
        payload=payload,
    )
    return {
        "proposal_id": action.pk,
        "status": "awaiting_student_approval",
        "task_title": task.title,
        "change": payload,
    }


@transaction.atomic
def approve_pending_action(user, action_id):
    """Apply one validated proposal only after its owner clicks Approve."""
    action = get_object_or_404(
        PendingAction.objects.select_for_update(),
        pk=action_id,
        owner=user,
        status=PendingAction.Status.PENDING,
    )
    payload = action.payload
    if action.action_type == PendingAction.ActionType.CREATE_TASK:
        subject = get_object_or_404(Subject, pk=payload["subject_id"], owner=user)
        task = AcademicTask.objects.create(
            subject=subject,
            title=payload["title"],
            task_type=payload["task_type"],
            due_date=date.fromisoformat(payload["due_date"]) if payload["due_date"] else None,
            priority=payload["priority"],
            estimated_minutes=payload["estimated_minutes"],
            details=payload["details"],
        )
        description = f"Created {task.title}."
    elif action.action_type == PendingAction.ActionType.UPDATE_TASK:
        task = get_object_or_404(
            AcademicTask.objects.filter(subject__owner=user), pk=payload["task_id"]
        )
        field = payload["field"]
        value = payload["value"]
        if field == "due_date" and value:
            value = date.fromisoformat(value)
        setattr(task, field, value)
        task.save(update_fields=[field, "updated_at"])
        description = f"Updated {task.title}."
    else:
        raise ValueError("This proposal type cannot be approved.")

    action.status = PendingAction.Status.APPROVED
    action.resolved_at = timezone.now()
    action.save(update_fields=["status", "resolved_at"])
    return description


def reject_pending_action(user, action_id):
    """Mark one of the student's proposals as rejected without changing tasks."""
    action = get_object_or_404(
        PendingAction,
        pk=action_id,
        owner=user,
        status=PendingAction.Status.PENDING,
    )
    action.status = PendingAction.Status.REJECTED
    action.resolved_at = timezone.now()
    action.save(update_fields=["status", "resolved_at"])

