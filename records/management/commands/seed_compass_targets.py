"""
Seed Body Compass target ranges into the database.

Personal values must be passed as CLI arguments — never hard-coded here.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from records.models import ProfileTarget
from records.profiles import get_or_create_default_profile

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Create a ProfileTarget range version from CLI values. "
        "Does not embed personal targets in source code."
    )

    def add_arguments(self, parser):
        parser.add_argument("--valid-from", default="2005-01-01")
        parser.add_argument("--weight-min", type=Decimal, required=True)
        parser.add_argument("--weight-max", type=Decimal, required=True)
        parser.add_argument("--fat-min", type=Decimal, required=True)
        parser.add_argument("--fat-max", type=Decimal, required=True)
        parser.add_argument("--muscle-min", type=Decimal, required=True)
        parser.add_argument("--muscle-max", type=Decimal, required=True)
        parser.add_argument(
            "--username",
            help="UI user whose default profile receives the target (optional).",
        )
        parser.add_argument(
            "--close-previous",
            action="store_true",
            help="Set valid_to on open targets to the day before valid-from.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        user = None
        if options.get("username"):
            try:
                user = User.objects.get(username=options["username"])
            except User.DoesNotExist as exc:
                raise CommandError(
                    f"User '{options['username']}' not found"
                ) from exc
        profile = get_or_create_default_profile(user=user)
        valid_from = date.fromisoformat(options["valid_from"])
        for lo, hi, label in (
            (options["weight_min"], options["weight_max"], "weight"),
            (options["fat_min"], options["fat_max"], "fat"),
            (options["muscle_min"], options["muscle_max"], "muscle"),
        ):
            if lo > hi:
                raise CommandError(f"{label} min must be <= max")

        target = ProfileTarget(
            profile=profile,
            valid_from=valid_from,
            weight_min_kg=options["weight_min"],
            weight_max_kg=options["weight_max"],
            body_fat_min_percent=options["fat_min"],
            body_fat_max_percent=options["fat_max"],
            muscle_min_percent=options["muscle_min"],
            muscle_max_percent=options["muscle_max"],
        )
        # Close + create share this atomic block (handle is @transaction.atomic):
        # failed validation rolls back any closed previous rows.
        if options["close_previous"]:
            for previous in profile.targets.filter(valid_to__isnull=True):
                if previous.valid_from < valid_from:
                    previous.valid_to = valid_from - timedelta(days=1)
                    previous.save(update_fields=["valid_to", "updated_at"])
        try:
            target.full_clean()
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        target.save()
        self.stdout.write(self.style.SUCCESS(f"Created ProfileTarget {target.id}"))
