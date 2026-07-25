from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
import os


class Command(BaseCommand):
    help = "Create an initial admin user when bootstrap env vars are set and no users exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_BOOTSTRAP_ADMIN_USER")
        password = os.environ.get("DJANGO_BOOTSTRAP_ADMIN_PASSWORD")
        if not username or not password:
            self.stdout.write("Bootstrap admin skipped (credentials not set).")
            return

        User = get_user_model()
        if User.objects.exists():
            self.stdout.write("Bootstrap admin skipped (users already exist).")
            return

        with transaction.atomic():
            User.objects.create_superuser(
                username=username,
                email=os.environ.get("DJANGO_BOOTSTRAP_ADMIN_EMAIL", ""),
                password=password,
            )
        self.stdout.write(self.style.SUCCESS(f"Created bootstrap admin '{username}'."))
