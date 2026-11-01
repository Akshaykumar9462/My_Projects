"""Validated forms used by the task and study-session pages."""

from django import forms

from .models import AcademicTask, StudyPreferences, StudySession, Subject


class SubjectForm(forms.ModelForm):
    """Collect a subject name and prevent confusing case-only duplicates."""

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    class Meta:
        model = Subject
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "For example, Biology"}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicate_subjects = Subject.objects.filter(owner=self.user, name__iexact=name)
        if self.instance.pk:
            duplicate_subjects = duplicate_subjects.exclude(pk=self.instance.pk)
        if duplicate_subjects.exists():
            raise forms.ValidationError("A subject with this name already exists.")
        return name

    def save(self, commit=True):
        subject = super().save(commit=False)
        subject.owner = self.user
        if commit:
            subject.save()
            self.save_m2m()
        return subject


class AcademicTaskForm(forms.ModelForm):
    """Collect and validate fields for an academic task."""

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.filter(owner=user)

    class Meta:
        model = AcademicTask
        fields = [
            "title",
            "task_type",
            "subject",
            "details",
            "due_date",
            "priority",
            "estimated_minutes",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "For example, Calculus problem set"}),
            "details": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional notes"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "estimated_minutes": forms.NumberInput(attrs={"min": 1, "max": 1440}),
        }
        help_texts = {
            "estimated_minutes": "Optional. Use a rough estimate of the remaining work.",
            "due_date": "Leave blank if this task does not have a deadline.",
        }


class StudySessionForm(forms.ModelForm):
    """Collect a study period and ensure its task belongs to its subject."""

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.filter(owner=user)
        self.fields["task"].queryset = AcademicTask.objects.filter(subject__owner=user)

    class Meta:
        model = StudySession
        fields = ["subject", "task", "study_date", "duration_minutes", "notes"]
        widgets = {
            "study_date": forms.DateInput(attrs={"type": "date"}),
            "duration_minutes": forms.NumberInput(attrs={"min": 1, "max": 1440}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional reflection"}),
        }
        help_texts = {
            "task": "Optional. Choose a task if the session was focused on one item.",
            "duration_minutes": "Enter a number from 1 to 1440 minutes.",
        }

    def clean(self):
        cleaned_data = super().clean()
        subject = cleaned_data.get("subject")
        task = cleaned_data.get("task")
        if subject and task and task.subject_id != subject.pk:
            self.add_error("task", "Choose a task from the selected subject.")
        return cleaned_data


class StudyPreferencesForm(forms.ModelForm):
    """Let the student choose the defaults used by the suggested day plan."""

    class Meta:
        model = StudyPreferences
        fields = [
            "daily_available_minutes",
            "preferred_session_minutes",
            "break_minutes",
        ]
        widgets = {
            "daily_available_minutes": forms.NumberInput(attrs={"min": 0, "max": 720}),
            "preferred_session_minutes": forms.NumberInput(attrs={"min": 10, "max": 90}),
            "break_minutes": forms.NumberInput(attrs={"min": 0, "max": 30}),
        }
        help_texts = {
            "daily_available_minutes": "Your usual study time for one day, from 0 to 720 minutes.",
            "preferred_session_minutes": "The planner splits larger tasks into sessions of this length.",
            "break_minutes": "Suggested rest time after each focus session; it is outside study minutes.",
        }

