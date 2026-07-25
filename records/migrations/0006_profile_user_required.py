# Require Profile.user once ownership is resolved.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def require_owners(apps, schema_editor):
    Profile = apps.get_model("records", "Profile")
    if Profile.objects.filter(user__isnull=True).exists():
        raise RuntimeError(
            "Profiles still have no owner. Create a UI user "
            "(python manage.py manage_body_user add --superuser), then "
            "python manage.py assign_profiles_to_user --username <owner>, "
            "then re-run migrate."
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0005_profile_user_ownership"),
    ]

    operations = [
        migrations.RunPython(require_owners, noop_reverse),
        migrations.AlterField(
            model_name="profile",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="body_profiles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
