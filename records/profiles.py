"""Resolve the single Profile owned by the authenticated UI user."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import Http404

from .models import Profile

User = get_user_model()


def ensure_user_has_profile(user) -> Profile:
    profile = Profile.objects.filter(user=user).first()
    if profile:
        return profile
    return Profile.objects.create(
        user=user,
        display_name=user.get_username(),
        height_cm="170.00",
        timezone=getattr(settings, "TIME_ZONE", "Europe/Paris"),
    )


def get_or_create_default_profile(user=None) -> Profile:
    """CLI helper — uses explicit user, or the first UI user."""
    if user is None:
        users = list(User.objects.order_by("id")[:2])
        if not users:
            raise RuntimeError(
                "No UI users exist. Create one with: "
                "python manage.py manage_body_user add --superuser"
            )
        user = users[0]
    return ensure_user_has_profile(user)


def get_active_profile(request) -> Profile:
    if not request.user.is_authenticated:
        raise Http404("Authentication required")
    return ensure_user_has_profile(request.user)
