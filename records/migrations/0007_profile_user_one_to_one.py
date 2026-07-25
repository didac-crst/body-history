# Enforce one Profile per UI user.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count


def assert_one_profile_per_user(apps, schema_editor):
    Profile = apps.get_model("records", "Profile")
    dupes = (
        Profile.objects.values("user_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    usernames = []
    User = apps.get_model(settings.AUTH_USER_MODEL)
    for row in dupes:
        user = User.objects.filter(pk=row["user_id"]).first()
        usernames.append(getattr(user, "username", str(row["user_id"])))
    if usernames:
        raise RuntimeError(
            "Cannot enforce one profile per user; multiple profiles exist for: "
            + ", ".join(usernames)
            + ". Resolve duplicates before migrating."
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0006_profile_user_required"),
    ]

    operations = [
        migrations.RunPython(assert_one_profile_per_user, noop_reverse),
        migrations.RemoveIndex(
            model_name="profile",
            name="profiles_user_id_created_idx",
        ),
        migrations.AlterField(
            model_name="profile",
            name="user",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="body_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
