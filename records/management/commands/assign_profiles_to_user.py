"""Transfer a profile to a UI user who has none (recovery helper)."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from records.models import Profile

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Assign an existing profile to a UI user who has none. "
        "Enforces one profile per user. Does not touch database credentials."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--profile-id", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{options['username']}' not found") from exc

        if Profile.objects.filter(user=user).exists():
            raise CommandError(
                f"User '{user.username}' already has a profile "
                "(one profile per user)."
            )

        try:
            profile = Profile.objects.get(pk=options["profile_id"])
        except Profile.DoesNotExist as exc:
            raise CommandError(
                f"Profile '{options['profile_id']}' not found"
            ) from exc

        previous = profile.user.get_username() if profile.user_id else "-"
        profile.user = user
        profile.save(update_fields=["user", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned profile '{profile.display_name}' to '{user.username}' "
                f"(previous owner: {previous})."
            )
        )
