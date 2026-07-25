"""
Manage Body History UI users (Django auth).

Does not touch database credentials (POSTGRES_*), secrets env files, or
anything outside Django's auth_user / related auth tables and owned profiles.
"""

from __future__ import annotations

import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from records.models import Profile
from records.trusted_devices import revoke_all_devices

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Create and manage UI login users only. "
        "Never alters POSTGRES_* credentials or secrets env files."
    )

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        add = sub.add_parser("add", help="Create a UI user (interactive by default)")
        add.add_argument("--username")
        add.add_argument("--email", default="")
        add.add_argument("--superuser", action="store_true")
        add.add_argument(
            "--no-profile",
            action="store_true",
            help="Do not create a default body profile",
        )
        add.add_argument("--display-name")
        add.add_argument("--height-cm", default="170.00")
        add.add_argument("--timezone", default="Europe/Madrid")
        add.add_argument(
            "--password-env",
            metavar="VAR",
            help="Read password from this environment variable (automation)",
        )
        add.add_argument(
            "--non-interactive",
            action="store_true",
            help="Require --username and password via --password-env; no prompts",
        )

        reset = sub.add_parser("reset-password", help="Reset a UI user password")
        reset.add_argument("--username", required=True)
        reset.add_argument("--password-env", metavar="VAR")

        deact = sub.add_parser("deactivate", help="Deactivate a UI user")
        deact.add_argument("--username", required=True)

        act = sub.add_parser("activate", help="Activate a UI user")
        act.add_argument("--username", required=True)

        sub.add_parser("list", help="List UI users")

        promote = sub.add_parser("promote", help="Grant staff/superuser")
        promote.add_argument("--username", required=True)
        promote.add_argument("--staff", action="store_true")
        promote.add_argument("--superuser", action="store_true")

        demote = sub.add_parser("demote", help="Remove staff/superuser")
        demote.add_argument("--username", required=True)
        demote.add_argument("--staff", action="store_true")
        demote.add_argument("--superuser", action="store_true")

    def handle(self, *args, **options):
        action = options["action"]
        handlers = {
            "add": self._add,
            "reset-password": self._reset_password,
            "deactivate": self._deactivate,
            "activate": self._activate,
            "list": self._list,
            "promote": self._promote,
            "demote": self._demote,
        }
        return handlers[action](**options)

    def _get_user(self, username: str):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{username}' not found") from exc

    def _read_password(self, *, password_env: str | None, non_interactive: bool = False) -> str:
        if password_env:
            value = os.environ.get(password_env)
            if not value:
                raise CommandError(
                    f"Environment variable {password_env} is empty or unset"
                )
            return value
        if non_interactive:
            raise CommandError("Non-interactive mode requires --password-env")
        first = getpass.getpass("Password: ")
        second = getpass.getpass("Password again: ")
        if first != second:
            raise CommandError("Passwords do not match")
        if not first:
            raise CommandError("Password cannot be empty")
        return first

    def _prompt(self, label: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default not in (None, "") else ""
        raw = input(f"{label}{suffix}: ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        return ""

    def _prompt_yn(self, label: str, default_yes: bool) -> bool:
        hint = "Y/n" if default_yes else "y/N"
        raw = input(f"{label} [{hint}]: ").strip().lower()
        if not raw:
            return default_yes
        return raw in {"y", "yes"}

    @transaction.atomic
    def _add(self, **options):
        non_interactive = options.get("non_interactive", False)
        username = options.get("username")
        email = options.get("email") or ""
        make_super = bool(options.get("superuser"))
        create_profile = not bool(options.get("no_profile"))
        display_name = options.get("display_name")
        height_cm = str(options.get("height_cm") or "170.00")
        tz = options.get("timezone") or "Europe/Madrid"
        password_env = options.get("password_env")

        if non_interactive:
            if not username:
                raise CommandError("--username is required with --non-interactive")
            password = self._read_password(
                password_env=password_env, non_interactive=True
            )
            display_name = display_name or username
        else:
            if not username:
                username = self._prompt("Username")
            email = self._prompt("Email", default=email)
            password = self._read_password(
                password_env=password_env, non_interactive=False
            )
            if not options.get("superuser"):
                make_super = self._prompt_yn("Superuser?", default_yes=False)
            if not options.get("no_profile"):
                create_profile = self._prompt_yn(
                    "Create profile for this user?", default_yes=True
                )
            if create_profile:
                display_name = display_name or self._prompt(
                    "Display name", default=username or ""
                )
                height_cm = self._prompt("Height cm", default=height_cm)
                tz = self._prompt("Timezone", default=tz)

        if not username:
            raise CommandError("Username is required")
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists")

        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        if make_super:
            user = User.objects.create_superuser(
                username=username, email=email or "", password=password
            )
        else:
            user = User.objects.create_user(
                username=username, email=email or "", password=password
            )

        if create_profile:
            Profile.objects.create(
                user=user,
                display_name=display_name or username,
                height_cm=height_cm,
                timezone=tz,
            )

        kind = "superuser" if user.is_superuser else "user"
        self.stdout.write(
            self.style.SUCCESS(f"Created UI {kind} '{username}' (password hashed).")
        )

    @transaction.atomic
    def _reset_password(self, **options):
        user = self._get_user(options["username"])
        password = self._read_password(password_env=options.get("password_env"))
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        user.set_password(password)
        user.save(update_fields=["password"])
        revoked = revoke_all_devices(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Password updated for '{user.username}' "
                f"(revoked {revoked} trusted device token(s))."
            )
        )

    @transaction.atomic
    def _deactivate(self, **options):
        user = self._get_user(options["username"])
        user.is_active = False
        user.save(update_fields=["is_active"])
        revoked = revoke_all_devices(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deactivated '{user.username}' "
                f"(revoked {revoked} trusted device token(s))."
            )
        )

    @transaction.atomic
    def _activate(self, **options):
        user = self._get_user(options["username"])
        user.is_active = True
        user.save(update_fields=["is_active"])
        self.stdout.write(self.style.SUCCESS(f"Activated '{user.username}'."))

    def _list(self, **options):
        users = User.objects.order_by("username")
        if not users.exists():
            self.stdout.write("No UI users.")
            return
        for user in users:
            has_profile = Profile.objects.filter(user=user).exists()
            last = user.last_login.isoformat() if user.last_login else "-"
            flags = []
            if user.is_active:
                flags.append("active")
            else:
                flags.append("inactive")
            if user.is_staff:
                flags.append("staff")
            if user.is_superuser:
                flags.append("superuser")
            self.stdout.write(
                f"{user.username}\temail={user.email or '-'}\t"
                f"{','.join(flags)}\tprofile={'yes' if has_profile else 'no'}\t"
                f"last_login={last}"
            )

    @transaction.atomic
    def _promote(self, **options):
        if not options.get("staff") and not options.get("superuser"):
            raise CommandError("Pass --staff and/or --superuser")
        user = self._get_user(options["username"])
        fields = []
        if options.get("staff"):
            user.is_staff = True
            fields.append("is_staff")
        if options.get("superuser"):
            user.is_superuser = True
            user.is_staff = True
            fields.extend(["is_superuser", "is_staff"])
        user.save(update_fields=sorted(set(fields)))
        self.stdout.write(self.style.SUCCESS(f"Promoted '{user.username}'."))

    @transaction.atomic
    def _demote(self, **options):
        if not options.get("staff") and not options.get("superuser"):
            raise CommandError("Pass --staff and/or --superuser")
        user = self._get_user(options["username"])
        fields = []
        if options.get("superuser"):
            user.is_superuser = False
            fields.append("is_superuser")
        if options.get("staff"):
            user.is_staff = False
            fields.append("is_staff")
        user.save(update_fields=fields)
        self.stdout.write(self.style.SUCCESS(f"Demoted '{user.username}'."))
