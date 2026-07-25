"""
Seed Body Compass target ranges into the database.

Personal values must be passed as CLI arguments — never hard-coded here.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from records.models import ProfileTarget
from records.views import get_or_create_default_profile


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
            "--close-previous",
            action="store_true",
            help="Set valid_to on open targets to the day before valid-from.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        profile = get_or_create_default_profile()
        valid_from = date.fromisoformat(options["valid_from"])
        for lo, hi, label in (
            (options["weight_min"], options["weight_max"], "weight"),
            (options["fat_min"], options["fat_max"], "fat"),
            (options["muscle_min"], options["muscle_max"], "muscle"),
        ):
            if lo > hi:
                raise CommandError(f"{label} min must be <= max")

        if options["close_previous"]:
            for target in profile.targets.filter(valid_to__isnull=True):
                if target.valid_from < valid_from:
                    target.valid_to = valid_from - timedelta(days=1)
                    target.save(update_fields=["valid_to", "updated_at"])

        target = ProfileTarget.objects.create(
            profile=profile,
            valid_from=valid_from,
            weight_min_kg=options["weight_min"],
            weight_max_kg=options["weight_max"],
            body_fat_min_percent=options["fat_min"],
            body_fat_max_percent=options["fat_max"],
            muscle_min_percent=options["muscle_min"],
            muscle_max_percent=options["muscle_max"],
        )
        self.stdout.write(self.style.SUCCESS(f"Created ProfileTarget {target.id}"))
