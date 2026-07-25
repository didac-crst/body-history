"""Resolve per-profile Compass algorithm configuration."""

from __future__ import annotations

from .models import CompassPreferences, Profile
from .scoring import AlgorithmConfig


def resolve_algorithm(profile: Profile | None) -> AlgorithmConfig:
    if profile is None:
        return AlgorithmConfig.defaults()
    try:
        prefs = profile.compass_preferences
    except CompassPreferences.DoesNotExist:
        return AlgorithmConfig.defaults()
    return AlgorithmConfig(
        weight_importance=prefs.weight_importance,
        body_fat_importance=prefs.body_fat_importance,
        muscle_importance=prefs.muscle_importance,
        weight_soft_kg=prefs.weight_soft_kg,
        weight_hard_kg=prefs.weight_hard_kg,
        fat_soft_pp=prefs.fat_soft_pp,
        fat_hard_pp=prefs.fat_hard_pp,
        muscle_soft_pp=prefs.muscle_soft_pp,
        muscle_hard_pp=prefs.muscle_hard_pp,
        trend_window_days=prefs.trend_window_days,
        comparison_window_days=prefs.comparison_window_days,
    )


def get_or_create_preferences(profile: Profile) -> CompassPreferences:
    prefs, _ = CompassPreferences.objects.get_or_create(profile=profile)
    return prefs
