"""Active profile selection for multi-person household use."""

from __future__ import annotations

from django.conf import settings

from .models import Profile

SESSION_KEY = "active_profile_id"


def ensure_default_profile() -> Profile:
    profile = Profile.objects.order_by("created_at").first()
    if profile:
        return profile
    return Profile.objects.create(
        display_name="Default",
        height_cm="181.00",
        timezone=settings.TIME_ZONE,
    )


def get_or_create_default_profile() -> Profile:
    """CLI / non-request helper — first profile, created if missing."""
    return ensure_default_profile()


def list_profiles():
    ensure_default_profile()
    return Profile.objects.order_by("created_at")


def get_active_profile(request) -> Profile:
    ensure_default_profile()
    raw = request.session.get(SESSION_KEY)
    if raw:
        profile = Profile.objects.filter(pk=raw).first()
        if profile:
            return profile
    profile = Profile.objects.order_by("created_at").first()
    request.session[SESSION_KEY] = str(profile.id)
    return profile


def set_active_profile(request, profile: Profile) -> None:
    request.session[SESSION_KEY] = str(profile.id)
