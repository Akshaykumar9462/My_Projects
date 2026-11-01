"""Add sample study data without changing or deleting existing records."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academics.models import AcademicTask, StudySession, Subject


class Command(BaseCommand):
    help = "Add sample subjects, tasks, and a study session without overwriting existing rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            required=True,
            help="Add the sample records to this existing student's account.",
        )

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"No account exists with username '{options['username']}'.")

        today = timezone.localdate()
        subject_names = ["Mathematics", "Biology", "History"]
        subjects = {}
        created_subjects = 0

        for name in subject_names:
            subjects[name], created = Subject.objects.get_or_create(owner=user, name=name)
            created_subjects += int(created)

        task_examples = [
            {
                "title": "Calculus problem set",
                "task_type": AcademicTask.TaskType.ASSIGNMENT,
                "subject": subjects["Mathematics"],
                "due_date": today + timedelta(days=2),
                "priority": AcademicTask.Priority.HIGH,
                "estimated_minutes": 90,
                "status": AcademicTask.Status.IN_PROGRESS,
                "details": "Sample task. Safe to edit or delete from the dashboard.",
            },
            {
                "title": "Biology practice exam",
                "task_type": AcademicTask.TaskType.EXAM,
                "subject": subjects["Biology"],
                "due_date": today + timedelta(days=6),
                "priority": AcademicTask.Priority.MEDIUM,
                "estimated_minutes": 120,
                "status": AcademicTask.Status.NOT_STARTED,
                "details": "Sample task. Safe to edit or delete from the dashboard.",
            },
            {
                "title": "History project outline",
                "task_type": AcademicTask.TaskType.PROJECT,
                "subject": subjects["History"],
                "due_date": today - timedelta(days=1),
                "priority": AcademicTask.Priority.MEDIUM,
                "estimated_minutes": 45,
                "status": AcademicTask.Status.COMPLETED,
                "details": "Sample task. Safe to edit or delete from the dashboard.",
            },
        ]
        created_tasks = 0
        for task_data in task_examples:
            _, created = AcademicTask.objects.get_or_create(
                title=task_data["title"],
                subject=task_data["subject"],
                defaults=task_data,
            )
            created_tasks += int(created)

        _, created_session = StudySession.objects.get_or_create(
            subject=subjects["Mathematics"],
            study_date=today,
            duration_minutes=35,
            notes="Sample study session.",
            defaults={
                "task": AcademicTask.objects.filter(
                    title="Calculus problem set",
                    subject=subjects["Mathematics"],
                ).first(),
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data ready: "
                f"{created_subjects} subjects, {created_tasks} tasks, "
                f"{int(created_session)} study session added. Existing records were not overwritten."
            )
        )

