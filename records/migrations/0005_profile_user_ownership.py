# Add nullable Profile.user and assign when ownership is unambiguous.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def assign_unowned_profiles(apps, schema_editor):
    Profile = apps.get_model("records", "Profile")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    unowned = Profile.objects.filter(user__isnull=True)
    if not unowned.exists():
        return
    users = list(User.objects.order_by("id"))
    if len(users) == 1:
        unowned.update(user=users[0])
        return
    if len(users) == 0:
        # Leave null; 0006 will instruct the operator after a UI user exists.
        return
    raise RuntimeError(
        "Multiple UI users exist and profiles have no owner. "
        "Run: python manage.py assign_profiles_to_user --username <owner> "
        "then migrate again."
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("records", "0004_compasspreferences"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="user",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="body_profiles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_unowned_profiles, noop_reverse),
        migrations.AddIndex(
            model_name="profile",
            index=models.Index(
                fields=["user", "created_at"], name="profiles_user_id_created_idx"
            ),
        ),
    ]
