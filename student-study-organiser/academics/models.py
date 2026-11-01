"""Database models for subjects, academic work, and study sessions."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.conf import settings
from django.db import models
from django.utils import timezone


class Subject(models.Model):
    """A course or subject that academic tasks belong to."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_subjects",
    )
    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_subject_name_per_owner",
            ),
        ]

    def __str__(self):
        return self.name


class AcademicTask(models.Model):
    """An assignment, exam, or project with a deadline and progress status."""

    class TaskType(models.TextChoices):
        ASSIGNMENT = "assignment", "Assignment"
        EXAM = "exam", "Exam"
        PROJECT = "project", "Project"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    title = models.CharField(max_length=120)
    task_type = models.CharField(max_length=20, choices=TaskType.choices)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    details = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    estimated_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "title"]

    def __str__(self):
        return self.title


class StudySession(models.Model):
    """A study period that a student has chosen to record."""

    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="study_sessions",
    )
    task = models.ForeignKey(
        AcademicTask,
        on_delete=models.SET_NULL,
        related_name="study_sessions",
        null=True,
        blank=True,
    )
    study_date = models.DateField(default=timezone.localdate)
    duration_minutes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-study_date", "-created_at"]

    def __str__(self):
        return f"{self.subject}: {self.duration_minutes} minutes on {self.study_date}"


class StudyPreferences(models.Model):
    """Saved defaults the student can tune for daily study suggestions."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_preferences",
    )
    daily_available_minutes = models.PositiveSmallIntegerField(
        default=120,
        validators=[MinValueValidator(0), MaxValueValidator(720)],
    )
    preferred_session_minutes = models.PositiveSmallIntegerField(
        default=25,
        validators=[MinValueValidator(10), MaxValueValidator(90)],
    )
    break_minutes = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Study preferences for {self.owner}"


class StudyConversation(models.Model):
    """One saved assistant conversation for each student's account."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_conversation",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Study assistant conversation for {self.owner}"


class ChatMessage(models.Model):
    """A message saved as part of a student's assistant history."""

    class Role(models.TextChoices):
        USER = "user", "Student"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        StudyConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.get_role_display()} message at {self.created_at}"


class PendingAction(models.Model):
    """A proposed task change that only takes effect after student approval."""

    class ActionType(models.TextChoices):
        CREATE_TASK = "create_task", "Create task"
        UPDATE_TASK = "update_task", "Update task"

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_study_actions",
    )
    conversation = models.ForeignKey(
        StudyConversation,
        on_delete=models.CASCADE,
        related_name="pending_actions",
    )
    action_type = models.CharField(max_length=20, choices=ActionType.choices)
    payload = models.JSONField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_type_display()} ({self.get_status_display()})"

