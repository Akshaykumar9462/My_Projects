"""Assign existing local subjects to a locked owner before enabling accounts."""

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


LEGACY_USERNAME = "__local_demo_owner__"


def assign_existing_subjects(apps, schema_editor):
    """Preserve pre-account sample rows without making them publicly visible."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Subject = apps.get_model("academics", "Subject")
    database = schema_editor.connection.alias
    legacy_user, _ = User.objects.using(database).get_or_create(
        username=LEGACY_USERNAME,
        defaults={"is_active": False, "password": "!"},
    )
    if legacy_user.is_active:
        legacy_user.is_active = False
        legacy_user.password = "!"
        legacy_user.save(using=database, update_fields=["is_active", "password"])
    Subject.objects.using(database).filter(owner__isnull=True).update(owner=legacy_user)


def unassign_legacy_subjects(apps, schema_editor):
    """Allow the schema change to reverse when legacy rows still use that owner."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Subject = apps.get_model("academics", "Subject")
    database = schema_editor.connection.alias
    legacy_user = User.objects.using(database).filter(username=LEGACY_USERNAME).first()
    if legacy_user:
        Subject.objects.using(database).filter(owner=legacy_user).update(owner=None)


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="subject",
            name="name",
            field=models.CharField(max_length=80),
        ),
        migrations.AddField(
            model_name="subject",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="study_subjects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_existing_subjects, unassign_legacy_subjects),
        migrations.AddConstraint(
            model_name="subject",
            constraint=models.UniqueConstraint(
                fields=("owner", "name"),
                name="unique_subject_name_per_owner",
            ),
        ),
        migrations.AlterField(
            model_name="subject",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="study_subjects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

