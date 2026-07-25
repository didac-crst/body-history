from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from records.models import TrustedDevice
from records.trusted_devices import hash_token


pytestmark = pytest.mark.django_db

User = get_user_model()
STRONG = "BodyHistory-Test-Pass-9!"


def test_manage_body_user_add_hashes_password(monkeypatch):
    monkeypatch.setenv("BH_TEST_PW", STRONG)
    out = StringIO()
    call_command(
        "manage_body_user",
        "add",
        "--username",
        "alice",
        "--email",
        "alice@example.com",
        "--superuser",
        "--non-interactive",
        "--password-env",
        "BH_TEST_PW",
        stdout=out,
    )
    user = User.objects.get(username="alice")
    assert user.body_profile is not None
    assert user.check_password(STRONG)
    assert user.password != STRONG
    assert user.is_superuser
    assert "hashed" in out.getvalue().lower()


def test_manage_body_user_reset_password_revokes_devices(monkeypatch):
    user = User.objects.create_user(username="bob", password="old-pass-value")
    TrustedDevice.objects.create(
        user=user,
        token_hash=hash_token("device-token"),
        label="phone",
        expires_at=timezone.now() + timedelta(days=10),
    )
    monkeypatch.setenv("BH_TEST_PW2", STRONG)
    call_command(
        "manage_body_user",
        "reset-password",
        "--username",
        "bob",
        "--password-env",
        "BH_TEST_PW2",
    )
    user.refresh_from_db()
    assert user.check_password(STRONG)
    assert not TrustedDevice.objects.filter(user=user, revoked_at__isnull=True).exists()


def test_manage_body_user_deactivate_and_activate():
    user = User.objects.create_user(username="carol", password=STRONG)
    TrustedDevice.objects.create(
        user=user,
        token_hash=hash_token("carol-token"),
        label="laptop",
        expires_at=timezone.now() + timedelta(days=10),
    )
    call_command("manage_body_user", "deactivate", "--username", "carol")
    user.refresh_from_db()
    assert user.is_active is False
    assert not TrustedDevice.objects.filter(user=user, revoked_at__isnull=True).exists()

    call_command("manage_body_user", "activate", "--username", "carol")
    user.refresh_from_db()
    assert user.is_active is True


def test_manage_body_user_list_includes_flags():
    User.objects.create_superuser(username="admin", email="", password=STRONG)
    out = StringIO()
    call_command("manage_body_user", "list", stdout=out)
    text = out.getvalue()
    assert "admin" in text
    assert "superuser" in text
