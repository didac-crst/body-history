from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    ProfileTarget = apps.get_model("records", "ProfileTarget")
    half = Decimal("0.50")
    for target in ProfileTarget.objects.all():
        changed = False
        if target.weight_min_kg is None and target.weight_max_kg is None and target.target_weight_kg is not None:
            target.weight_min_kg = target.target_weight_kg - half
            target.weight_max_kg = target.target_weight_kg + half
            changed = True
        if (
            target.body_fat_min_percent is None
            and target.body_fat_max_percent is None
            and target.target_body_fat_percent is not None
        ):
            target.body_fat_min_percent = target.target_body_fat_percent - half
            target.body_fat_max_percent = target.target_body_fat_percent + half
            changed = True
        if (
            target.muscle_min_percent is None
            and target.muscle_max_percent is None
            and target.target_muscle_percent is not None
        ):
            target.muscle_min_percent = target.target_muscle_percent - half
            target.muscle_max_percent = target.target_muscle_percent + half
            changed = True
        if changed:
            target.save()


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("records", "0002_profiletarget_body_fat_max_percent_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
