"""Settings helpers: target preview against current trend."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .compass import effective_target_ranges
from .guidance import fitness_signals
from .metrics import target_for_date
from .models import Profile
from .preferences import resolve_algorithm
from .trends import trend_average


def target_preview(profile: Profile) -> dict[str, Any] | None:
    """Compare recent trend to active target + soft/hard outer bands."""
    from django.utils import timezone

    on_date = timezone.localdate()
    target = target_for_date(profile, on_date)
    ranges = effective_target_ranges(target)
    if target is None or not any(ranges.values()):
        return None

    algo = resolve_algorithm(profile)
    trend_days = algo.trend_window_days
    trend = {
        "weight_kg": trend_average(profile, "weight_kg", days=trend_days),
        "body_fat_percent": trend_average(profile, "body_fat_percent", days=trend_days),
        "muscle_percent": trend_average(profile, "muscle_percent", days=trend_days),
        "window_days": trend_days,
    }

    def _band(lo, hi, soft, hard):
        if lo is None or hi is None:
            return None
        return {
            "ideal_min": float(lo),
            "ideal_max": float(hi),
            "soft_min": float(lo - soft),
            "soft_max": float(hi + soft),
            "hard_min": float(lo - hard),
            "hard_max": float(hi + hard),
        }

    bands = {
        "weight": _band(
            ranges.get("weight_min"),
            ranges.get("weight_max"),
            algo.weight_soft_kg,
            algo.weight_hard_kg,
        ),
        "body_fat": _band(
            ranges.get("fat_min"),
            ranges.get("fat_max"),
            algo.fat_soft_pp,
            algo.fat_hard_pp,
        ),
        "muscle": _band(
            ranges.get("muscle_min"),
            ranges.get("muscle_max"),
            algo.muscle_soft_pp,
            algo.muscle_hard_pp,
        ),
    }

    signals = fitness_signals(
        height_cm=profile.height_cm,
        weight_kg=trend["weight_kg"],
        body_fat_percent=trend["body_fat_percent"],
        target=ranges,
    )

    def _pos(value, band):
        if value is None or band is None:
            return None
        v = float(value)
        if band["ideal_min"] <= v <= band["ideal_max"]:
            return "ideal"
        if band["soft_min"] <= v <= band["soft_max"]:
            return "soft"
        if band["hard_min"] <= v <= band["hard_max"]:
            return "hard"
        return "beyond"

    return {
        "valid_from": target.valid_from.isoformat(),
        "valid_to": target.valid_to.isoformat() if target.valid_to else None,
        "trend": {
            "weight_kg": float(trend["weight_kg"]) if trend["weight_kg"] is not None else None,
            "body_fat_percent": float(trend["body_fat_percent"])
            if trend["body_fat_percent"] is not None
            else None,
            "muscle_percent": float(trend["muscle_percent"])
            if trend["muscle_percent"] is not None
            else None,
            "window_days": trend_days,
        },
        "bands": bands,
        "positions": {
            "weight": _pos(trend["weight_kg"], bands["weight"]),
            "body_fat": _pos(trend["body_fat_percent"], bands["body_fat"]),
            "muscle": _pos(trend["muscle_percent"], bands["muscle"]),
        },
        "signals": signals,
    }
