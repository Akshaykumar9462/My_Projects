"""Tests for database-backed tasks and study tracking."""

from datetime import timedelta
import json
from types import SimpleNamespace

import httpx
from openai import OpenAI
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    AcademicTask,
    ChatMessage,
    PendingAction,
    StudyConversation,
    StudyPreferences,
    StudySession,
    Subject,
)
from .services.assistant import generate_reply
from .services.planning import build_study_plan
from study_organiser.database import database_configuration
from .services.progress import build_progress_summary


class PublicDiscoveryTests(SimpleTestCase):
    def test_homepage_is_public_and_search_indexable(self):
        response = self.client.get(reverse("academics:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Organise academic tasks")
        self.assertContains(response, '<meta name="robots" content="index,follow">', html=True)
        self.assertContains(
            response,
            '<link rel="canonical" href="http://testserver/">',
            html=True,
        )

    def test_sitemap_lists_only_the_public_homepage(self):
        response = self.client.get(reverse("sitemap"))
        sitemap = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/xml"))
        self.assertIn("<loc>http://testserver/</loc>", sitemap)
        self.assertNotIn("/dashboard/", sitemap)
        self.assertNotIn("/study-plan/", sitemap)

    def test_robots_file_points_to_sitemap(self):
        response = self.client.get(reverse("robots"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("User-agent: *", response.content.decode())
        self.assertIn("Allow: /", response.content.decode())
        self.assertIn("Sitemap: http://testserver/sitemap.xml", response.content.decode())

    def test_login_and_signup_pages_are_not_indexed(self):
        for url_name in ("login", "signup"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    '<meta name="robots" content="noindex,follow">',
                    html=True,
                )


class AcademicPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("student-one", password="test-pass-123")
        self.client.force_login(self.user)
        self.subject = Subject.objects.create(owner=self.user, name="Mathematics")
        today = timezone.localdate()
        self.task = AcademicTask.objects.create(
            title="Calculus problem set",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=self.subject,
            due_date=today + timedelta(days=2),
            priority=AcademicTask.Priority.HIGH,
            estimated_minutes=90,
            status=AcademicTask.Status.IN_PROGRESS,
        )
        StudySession.objects.create(
            subject=self.subject,
            task=self.task,
            study_date=today,
            duration_minutes=35,
        )

    def test_dashboard_uses_saved_tasks_and_study_sessions(self):
        response = self.client.get(reverse("academics:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calculus problem set")
        self.assertContains(response, '<meta name="robots" content="noindex,follow">', html=True)

    def test_authenticated_homepage_redirects_to_the_dashboard(self):
        response = self.client.get(reverse("academics:home"))

        self.assertRedirects(response, reverse("academics:dashboard"))

    def test_authenticated_homepage_redirects_to_the_dashboard(self):
        response = self.client.get(reverse("academics:home"))

        self.assertRedirects(response, reverse("academics:dashboard"))
        self.assertEqual(response.context["total_count"], 1)
        self.assertEqual(response.context["pending_count"], 1)
        self.assertEqual(response.context["study_minutes_this_week"], 35)

    def test_empty_dashboard_shows_a_useful_next_step(self):
        AcademicTask.objects.all().delete()

        response = self.client.get(reverse("academics:dashboard"))

        self.assertEqual(response.context["progress_percent"], 0)
        self.assertContains(response, "No tasks yet")
        self.assertContains(response, "Add a task")

    def test_subject_list_shows_saved_subjects(self):
        response = self.client.get(reverse("academics:subjects"))

        self.assertContains(response, "Mathematics")


class TaskFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("student-two", password="test-pass-123")
        self.client.force_login(self.user)
        self.subject = Subject.objects.create(owner=self.user, name="Biology")

    def task_form_data(self, **overrides):
        data = {
            "title": "Cell structure assignment",
            "task_type": AcademicTask.TaskType.ASSIGNMENT,
            "subject": self.subject.pk,
            "details": "Review the class notes.",
            "due_date": (timezone.localdate() + timedelta(days=4)).isoformat(),
            "priority": AcademicTask.Priority.MEDIUM,
            "estimated_minutes": "60",
            "status": AcademicTask.Status.NOT_STARTED,
        }
        data.update(overrides)
        return data

    def test_student_can_create_a_task(self):
        response = self.client.post(
            reverse("academics:task-create"),
            self.task_form_data(),
        )

        self.assertRedirects(response, reverse("academics:dashboard"))
        self.assertEqual(AcademicTask.objects.count(), 1)
        self.assertEqual(AcademicTask.objects.get().subject, self.subject)

    def test_invalid_task_is_not_saved(self):
        response = self.client.post(
            reverse("academics:task-create"),
            self.task_form_data(title="", estimated_minutes="0"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AcademicTask.objects.count(), 0)
        self.assertTrue(response.context["form"].errors)

    def test_student_can_update_a_task(self):
        task = AcademicTask.objects.create(
            title="Cell worksheet",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=self.subject,
        )

        response = self.client.post(
            reverse("academics:task-update", args=[task.pk]),
            self.task_form_data(status=AcademicTask.Status.COMPLETED),
        )

        task.refresh_from_db()
        self.assertRedirects(response, reverse("academics:dashboard"))
        self.assertEqual(task.title, "Cell structure assignment")
        self.assertEqual(task.status, AcademicTask.Status.COMPLETED)

    def test_task_delete_requires_a_confirmation_post(self):
        task = AcademicTask.objects.create(
            title="Delete confirmation example",
            task_type=AcademicTask.TaskType.PROJECT,
            subject=self.subject,
        )

        confirmation = self.client.get(reverse("academics:task-delete", args=[task.pk]))
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(AcademicTask.objects.count(), 1)

        response = self.client.post(reverse("academics:task-delete", args=[task.pk]))
        self.assertRedirects(response, reverse("academics:dashboard"))
        self.assertEqual(AcademicTask.objects.count(), 0)


class SubjectAndStudySessionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("student-three", password="test-pass-123")
        self.client.force_login(self.user)
        self.subject = Subject.objects.create(owner=self.user, name="Physics")

    def test_subject_creation_trims_whitespace(self):
        response = self.client.post(
            reverse("academics:subject-create"),
            {"name": "  Chemistry  "},
        )

        self.assertRedirects(response, reverse("academics:subjects"))
        self.assertTrue(Subject.objects.filter(name="Chemistry").exists())

    def test_duplicate_subject_name_is_rejected_case_insensitively(self):
        response = self.client.post(
            reverse("academics:subject-create"),
            {"name": "physics"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subject.objects.count(), 1)
        self.assertTrue(response.context["form"].errors)

    def test_study_session_can_be_logged(self):
        response = self.client.post(
            reverse("academics:study-session-create"),
            {
                "subject": self.subject.pk,
                "task": "",
                "study_date": timezone.localdate().isoformat(),
                "duration_minutes": "45",
                "notes": "Revised lecture notes.",
            },
        )

        self.assertRedirects(response, reverse("academics:dashboard"))
        self.assertEqual(StudySession.objects.get().duration_minutes, 45)

    def test_session_cannot_link_a_task_from_another_subject(self):
        another_subject = Subject.objects.create(owner=self.user, name="Chemistry")
        task = AcademicTask.objects.create(
            title="Physics report",
            task_type=AcademicTask.TaskType.PROJECT,
            subject=self.subject,
        )

        response = self.client.post(
            reverse("academics:study-session-create"),
            {
                "subject": another_subject.pk,
                "task": task.pk,
                "study_date": timezone.localdate().isoformat(),
                "duration_minutes": "30",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudySession.objects.count(), 0)
        self.assertIn("task", response.context["form"].errors)


class DemoDataCommandTests(TestCase):
    def test_demo_data_command_is_repeatable_and_preserves_matching_task(self):
        user = get_user_model().objects.create_user("demo-student", password="test-pass-123")
        mathematics = Subject.objects.create(owner=user, name="Mathematics")
        existing_task = AcademicTask.objects.create(
            title="Calculus problem set",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=mathematics,
            details="My own notes should remain unchanged.",
        )

        call_command("seed_demo_data", username=user.username)
        existing_task.refresh_from_db()
        first_counts = (
            Subject.objects.filter(owner=user).count(),
            AcademicTask.objects.filter(subject__owner=user).count(),
            StudySession.objects.filter(subject__owner=user).count(),
        )

        call_command("seed_demo_data", username=user.username)
        existing_task.refresh_from_db()
        second_counts = (
            Subject.objects.filter(owner=user).count(),
            AcademicTask.objects.filter(subject__owner=user).count(),
            StudySession.objects.filter(subject__owner=user).count(),
        )

        self.assertEqual(first_counts, (3, 3, 1))
        self.assertEqual(second_counts, first_counts)
        self.assertEqual(existing_task.details, "My own notes should remain unchanged.")


class ProgressSummaryTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.user = get_user_model().objects.create_user("student-four", password="test-pass-123")
        self.subject = Subject.objects.create(owner=self.user, name="Computer Science")

    def make_task(self, title, due_date, status=AcademicTask.Status.NOT_STARTED):
        return AcademicTask.objects.create(
            title=title,
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=self.subject,
            due_date=due_date,
            status=status,
        )

    def test_overdue_and_due_soon_counts_ignore_completed_tasks(self):
        self.make_task("Late essay", self.today - timedelta(days=2))
        self.make_task(
            "Upcoming lab report",
            self.today + timedelta(days=1),
            status=AcademicTask.Status.IN_PROGRESS,
        )
        self.make_task(
            "Finished old assignment",
            self.today - timedelta(days=5),
            status=AcademicTask.Status.COMPLETED,
        )

        summary = build_progress_summary(self.user, today=self.today)

        self.assertEqual(summary["overdue_count"], 1)
        self.assertEqual(summary["due_soon_count"], 1)
        self.assertEqual(summary["completed_count"], 1)
        self.assertEqual(summary["progress_percent"], 33)
        self.assertEqual(summary["suggestions"][0]["title"], "Review an overdue task")

    def test_study_minutes_compare_this_week_with_last_week(self):
        week_start = self.today - timedelta(days=self.today.weekday())
        StudySession.objects.create(
            subject=self.subject,
            study_date=self.today,
            duration_minutes=35,
        )
        StudySession.objects.create(
            subject=self.subject,
            study_date=week_start - timedelta(days=3),
            duration_minutes=50,
        )

        summary = build_progress_summary(self.user, today=self.today)

        self.assertEqual(summary["study_minutes_this_week"], 35)
        self.assertEqual(summary["study_minutes_last_week"], 50)
        self.assertEqual(summary["study_time_change_label"], "15 fewer minutes than last week")

    def test_empty_progress_summary_invites_student_to_add_a_task(self):
        summary = build_progress_summary(self.user, today=self.today)

        self.assertEqual(summary["total_count"], 0)
        self.assertEqual(summary["progress_percent"], 0)
        self.assertEqual(summary["suggestions"][0]["title"], "Add your first task")


class AccountIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("owner-one", password="test-pass-123")
        self.other_user = User.objects.create_user("owner-two", password="test-pass-123")
        self.subject = Subject.objects.create(owner=self.user, name="Physics")
        self.other_subject = Subject.objects.create(owner=self.other_user, name="Physics")
        self.task = AcademicTask.objects.create(
            title="My lab report",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=self.subject,
        )
        self.other_task = AcademicTask.objects.create(
            title="Private essay",
            task_type=AcademicTask.TaskType.PROJECT,
            subject=self.other_subject,
        )
        self.client.force_login(self.user)

    def test_private_pages_redirect_anonymous_students_to_login(self):
        self.client.logout()

        response = self.client.get(reverse("academics:dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('academics:dashboard')}",
            fetch_redirect_response=False,
        )

    def test_dashboard_only_shows_signed_in_students_records(self):
        response = self.client.get(reverse("academics:dashboard"))

        self.assertContains(response, "My lab report")
        self.assertNotContains(response, "Private essay")
        self.assertEqual(response.context["subject_count"], 1)
        self.assertEqual(response.context["total_count"], 1)

    def test_other_students_task_cannot_be_updated_or_deleted(self):
        update_response = self.client.get(
            reverse("academics:task-update", args=[self.other_task.pk])
        )
        delete_response = self.client.get(
            reverse("academics:task-delete", args=[self.other_task.pk])
        )

        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(AcademicTask.objects.filter(pk=self.other_task.pk).exists())

    def test_form_rejects_another_students_subject_id(self):
        response = self.client.post(
            reverse("academics:task-create"),
            {
                "title": "Unexpected task",
                "task_type": AcademicTask.TaskType.ASSIGNMENT,
                "subject": self.other_subject.pk,
                "status": AcademicTask.Status.NOT_STARTED,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AcademicTask.objects.count(), 2)
        self.assertIn("subject", response.context["form"].errors)

    def test_signup_claims_legacy_sample_records_and_signs_student_in(self):
        self.client.logout()
        legacy_user, _ = get_user_model().objects.get_or_create(
            username="__local_demo_owner__",
            defaults={"password": "!", "is_active": False},
        )
        legacy_subject = Subject.objects.create(owner=legacy_user, name="Sample Biology")
        legacy_task = AcademicTask.objects.create(
            title="Sample lab",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=legacy_subject,
        )

        response = self.client.post(
            reverse("signup"),
            {"username": "new-student", "password1": "Valid-pass-573!", "password2": "Valid-pass-573!"},
        )

        new_user = get_user_model().objects.get(username="new-student")
        legacy_subject.refresh_from_db()
        self.assertRedirects(response, reverse("academics:dashboard"))
        self.assertEqual(legacy_subject.owner, new_user)
        self.assertTrue(AcademicTask.objects.filter(pk=legacy_task.pk).exists())
        self.assertEqual(int(self.client.session.get("_auth_user_id")), new_user.pk)


class AssistantAgentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("assistant-student", password="test-pass-123")
        self.other_user = get_user_model().objects.create_user("assistant-other", password="test-pass-123")
        self.subject = Subject.objects.create(owner=self.user, name="Chemistry")
        self.other_subject = Subject.objects.create(owner=self.other_user, name="Chemistry")
        self.conversation = StudyConversation.objects.create(owner=self.user)
        self.client.force_login(self.user)

    def fake_client_for_tool(self, tool_name, arguments):
        tool_response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name=tool_name,
                    arguments=json.dumps(arguments),
                    call_id="call-test-1",
                )
            ],
            output_text="",
        )
        final_response = SimpleNamespace(output=[], output_text="I have prepared that for review.")

        class FakeResponses:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return tool_response if len(self.calls) == 1 else final_response

        client = SimpleNamespace(responses=FakeResponses())
        return client

    def test_assistant_chat_requires_sign_in(self):
        self.client.logout()

        response = self.client.get(reverse("academics:assistant"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_natural_language_message_is_saved_when_api_key_is_missing(self):
        with override_settings(OPENAI_API_KEY=""):
            response = self.client.post(
                reverse("academics:assistant"),
                {"message": "How am I doing this week?"},
            )

        self.assertRedirects(response, reverse("academics:assistant"))
        self.assertEqual(self.conversation.messages.count(), 2)
        self.assertContains(
            self.client.get(reverse("academics:assistant")),
            "Set OPENAI_API_KEY",
        )

    def test_create_tool_only_prepares_a_proposal_until_student_approves(self):
        ChatMessage.objects.create(
            conversation=self.conversation,
            role=ChatMessage.Role.USER,
            content="Add a Chemistry assignment called Lab report due 2030-04-05.",
        )
        client = self.fake_client_for_tool(
            "propose_create_task",
            {
                "title": "Lab report",
                "subject_name": "Chemistry",
                "task_type": "assignment",
                "due_date": "2030-04-05",
                "priority": "medium",
                "estimated_minutes": 60,
                "details": "",
            },
        )

        reply = generate_reply(self.user, self.conversation, client=client)

        action = PendingAction.objects.get(owner=self.user)
        self.assertEqual(reply, "I have prepared that for review.")
        self.assertEqual(AcademicTask.objects.count(), 0)
        self.assertEqual(action.status, PendingAction.Status.PENDING)
        self.assertEqual(len(client.responses.calls), 2)
        self.assertEqual(
            client.responses.calls[1]["input"][-1]["type"],
            "function_call_output",
        )

        response = self.client.post(
            reverse("academics:assistant-action-approve", args=[action.pk])
        )

        self.assertRedirects(response, reverse("academics:assistant"))
        self.assertEqual(AcademicTask.objects.filter(subject=self.subject).count(), 1)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.APPROVED)

    def test_dismissed_proposal_does_not_change_task_records(self):
        action = PendingAction.objects.create(
            owner=self.user,
            conversation=self.conversation,
            action_type=PendingAction.ActionType.CREATE_TASK,
            payload={"title": "Not created"},
        )

        response = self.client.post(
            reverse("academics:assistant-action-reject", args=[action.pk])
        )

        self.assertRedirects(response, reverse("academics:assistant"))
        self.assertEqual(AcademicTask.objects.count(), 0)
        action.refresh_from_db()
        self.assertEqual(action.status, PendingAction.Status.REJECTED)

    def test_update_tool_waits_for_approval_before_changing_a_task(self):
        task = AcademicTask.objects.create(
            title="Chemistry worksheet",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=self.subject,
            status=AcademicTask.Status.NOT_STARTED,
        )
        client = self.fake_client_for_tool(
            "propose_update_task",
            {"task_id": task.pk, "field": "status", "value": "completed"},
        )

        generate_reply(self.user, self.conversation, client=client)

        task.refresh_from_db()
        action = PendingAction.objects.get(owner=self.user)
        self.assertEqual(task.status, AcademicTask.Status.NOT_STARTED)
        self.client.post(reverse("academics:assistant-action-approve", args=[action.pk]))
        task.refresh_from_db()
        self.assertEqual(task.status, AcademicTask.Status.COMPLETED)

    def test_student_cannot_approve_another_accounts_proposal(self):
        other_conversation = StudyConversation.objects.create(owner=self.other_user)
        action = PendingAction.objects.create(
            owner=self.other_user,
            conversation=other_conversation,
            action_type=PendingAction.ActionType.CREATE_TASK,
            payload={},
        )

        response = self.client.post(
            reverse("academics:assistant-action-approve", args=[action.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(AcademicTask.objects.count(), 0)

    def test_tool_results_only_contain_the_signed_in_students_tasks(self):
        own_task = AcademicTask.objects.create(
            title="Own assignment",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=self.subject,
        )
        AcademicTask.objects.create(
            title="Other account assignment",
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=self.other_subject,
        )
        client = self.fake_client_for_tool("list_tasks", {})

        reply = generate_reply(self.user, self.conversation, client=client)

        tool_result = json.loads(client.responses.calls[1]["input"][-1]["output"])
        self.assertEqual(reply, "I have prepared that for review.")
        self.assertEqual([task["title"] for task in tool_result["tasks"]], [own_task.title])

    def test_openai_sdk_tool_round_trip_works_with_offline_http_mock(self):
        ChatMessage.objects.create(
            conversation=self.conversation,
            role=ChatMessage.Role.USER,
            content="What subjects do I have?",
        )
        request_bodies = []

        def mock_response(request):
            request_bodies.append(json.loads(request.content))
            if len(request_bodies) == 1:
                output = [
                    {
                        "id": "fc_offline_test",
                        "type": "function_call",
                        "status": "completed",
                        "name": "list_subjects",
                        "arguments": "{}",
                        "call_id": "call_offline_test",
                    }
                ]
            else:
                output = [
                    {
                        "id": "msg_offline_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "You have Chemistry saved.",
                                "annotations": [],
                            }
                        ],
                    }
                ]
            return httpx.Response(
                200,
                json={
                    "id": f"resp_offline_{len(request_bodies)}",
                    "object": "response",
                    "created_at": 1793550000,
                    "status": "completed",
                    "model": "gpt-6-astra",
                    "output": output,
                },
            )

        http_client = httpx.Client(transport=httpx.MockTransport(mock_response))
        client = OpenAI(api_key="sk-offline-test", http_client=http_client)
        try:
            reply = generate_reply(self.user, self.conversation, client=client)
        finally:
            client.close()

        self.assertEqual(reply, "You have Chemistry saved.")
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(
            request_bodies[1]["input"][-1]["type"],
            "function_call_output",
        )
        self.assertIn("Chemistry", request_bodies[1]["input"][-1]["output"])


class StudyPlannerTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.user = get_user_model().objects.create_user("planner-student", password="test-pass-123")
        self.other_user = get_user_model().objects.create_user("planner-other", password="test-pass-123")
        self.subject = Subject.objects.create(owner=self.user, name="Literature")
        self.other_subject = Subject.objects.create(owner=self.other_user, name="Literature")
        self.client.force_login(self.user)

    def make_task(self, title, subject, due_date, estimated_minutes, priority="medium", status="not_started"):
        return AcademicTask.objects.create(
            title=title,
            task_type=AcademicTask.TaskType.ASSIGNMENT,
            subject=subject,
            due_date=due_date,
            estimated_minutes=estimated_minutes,
            priority=priority,
            status=status,
        )

    def test_planner_uses_deadline_priority_and_time_limit_without_changing_tasks(self):
        due_today = self.make_task(
            "Due today", self.subject, self.today, 10, priority=AcademicTask.Priority.LOW
        )
        near_task = self.make_task(
            "Due soon", self.subject, self.today + timedelta(days=2), 35
        )
        self.make_task(
            "Later high priority",
            self.subject,
            self.today + timedelta(days=5),
            50,
            priority=AcademicTask.Priority.HIGH,
        )
        self.make_task(
            "Other student's task",
            self.other_subject,
            self.today,
            30,
            priority=AcademicTask.Priority.HIGH,
        )
        completed = self.make_task(
            "Already finished",
            self.subject,
            self.today,
            30,
            status=AcademicTask.Status.COMPLETED,
        )
        StudyPreferences.objects.create(
            owner=self.user,
            daily_available_minutes=60,
            preferred_session_minutes=25,
            break_minutes=5,
        )

        plan = build_study_plan(self.user, today=self.today)

        self.assertEqual(plan["planned_minutes"], 60)
        self.assertEqual(plan["available_minutes"], 60)
        self.assertEqual(plan["focus_blocks"][0]["task"], due_today)
        self.assertEqual([block["task"] for block in plan["focus_blocks"][:2]], [due_today, near_task])
        self.assertNotIn(completed, [block["task"] for block in plan["focus_blocks"]])
        self.assertTrue(plan["unplanned_tasks"])
        self.assertEqual(AcademicTask.objects.count(), 5)

    def test_planner_uses_beginner_friendly_defaults_without_creating_preferences(self):
        plan = build_study_plan(self.user, today=self.today)

        self.assertEqual(plan["available_minutes"], 120)
        self.assertEqual(plan["session_minutes"], 25)
        self.assertEqual(StudyPreferences.objects.count(), 0)

    def test_student_can_save_personal_planning_preferences(self):
        response = self.client.post(
            reverse("academics:study-preferences"),
            {
                "daily_available_minutes": "90",
                "preferred_session_minutes": "30",
                "break_minutes": "10",
            },
        )

        self.assertRedirects(response, reverse("academics:study-plan"))
        preferences = StudyPreferences.objects.get(owner=self.user)
        self.assertEqual(preferences.daily_available_minutes, 90)
        self.assertEqual(preferences.preferred_session_minutes, 30)
        self.assertEqual(preferences.break_minutes, 10)

    def test_preference_validation_rejects_out_of_range_values(self):
        response = self.client.post(
            reverse("academics:study-preferences"),
            {
                "daily_available_minutes": "900",
                "preferred_session_minutes": "5",
                "break_minutes": "60",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudyPreferences.objects.get(owner=self.user).daily_available_minutes, 120)


class CloudDatabaseConfigTests(SimpleTestCase):
    def test_sqlite_remains_the_default_without_a_database_url(self):
        config = database_configuration(None, "local-study.sqlite3")

        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(str(config["NAME"]), "local-study.sqlite3")

    def test_postgres_url_is_parsed_without_losing_escaped_credentials(self):
        config = database_configuration(
            "postgresql://student%40account:p%3Ass%2Fword@db.example.test:5433/study_app?sslmode=verify-full",
            "unused.sqlite3",
        )

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "study_app")
        self.assertEqual(config["USER"], "student@account")
        self.assertEqual(config["PASSWORD"], "p:ss/word")
        self.assertEqual(config["HOST"], "db.example.test")
        self.assertEqual(config["PORT"], "5433")
        self.assertEqual(config["OPTIONS"]["sslmode"], "verify-full")
        self.assertEqual(config["CONN_MAX_AGE"], 60)

    def test_invalid_database_url_scheme_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            database_configuration("mysql://db.example.test/study", "unused.sqlite3")

