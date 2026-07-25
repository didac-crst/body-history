from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.utils import timezone

from .models import TrustedDevice

User = get_user_model()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_trusted_device(user, request, label: str = "") -> tuple[TrustedDevice, str]:
    raw = secrets.token_urlsafe(32)
    device = TrustedDevice.objects.create(
        user=user,
        token_hash=hash_token(raw),
        label=label or _default_label(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        expires_at=timezone.now()
        + timedelta(days=getattr(settings, "TRUSTED_DEVICE_DAYS", 180)),
    )
    return device, raw


def _default_label(request) -> str:
    ua = request.META.get("HTTP_USER_AGENT", "")
    if not ua:
        return "Trusted device"
    return ua[:80]


def set_trusted_device_cookie(response, raw_token: str) -> None:
    response.set_cookie(
        settings.TRUSTED_DEVICE_COOKIE_NAME,
        raw_token,
        max_age=getattr(settings, "TRUSTED_DEVICE_DAYS", 180) * 24 * 60 * 60,
        httponly=settings.TRUSTED_DEVICE_COOKIE_HTTPONLY,
        secure=settings.TRUSTED_DEVICE_COOKIE_SECURE,
        samesite=settings.TRUSTED_DEVICE_COOKIE_SAMESITE,
        path="/",
    )


def clear_trusted_device_cookie(response) -> None:
    response.delete_cookie(settings.TRUSTED_DEVICE_COOKIE_NAME, path="/")


def authenticate_trusted_device(request) -> User | None:
    raw = request.COOKIES.get(settings.TRUSTED_DEVICE_COOKIE_NAME)
    if not raw:
        return None
    device = (
        TrustedDevice.objects.select_related("user")
        .filter(token_hash=hash_token(raw), revoked_at__isnull=True)
        .first()
    )
    if device is None or not device.is_active:
        return None
    if not device.user.is_active:
        return None
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
    return device.user


def revoke_device(device: TrustedDevice) -> None:
    device.revoked_at = timezone.now()
    device.save(update_fields=["revoked_at"])


def revoke_all_devices(user) -> int:
    now = timezone.now()
    return TrustedDevice.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=now
    )


def login_from_trusted_device(request) -> bool:
    if request.user.is_authenticated:
        return False
    user = authenticate_trusted_device(request)
    if user is None:
        return False
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return True
