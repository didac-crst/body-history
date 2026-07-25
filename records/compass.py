"""Body Compass service — structured alignment overview from DB targets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from .guidance import action_guidance, fitness_signals
from .metrics import local_date, measurement_queryset, target_for_date
from .models import Measurement, Profile, ProfileTarget
from .preferences import resolve_algorithm
from .recommendations import Opportunity, rank_opportunities
from .scoring import (
    component_scores,
    components_to_dict,
    direction_label,
    overall_alignment,
)
from .trends import count_recent, recent_variability, trend_average


@dataclass
class CompassSnapshot:
    alignment: Decimal | None
    confidence: str
    freshness: str
    direction: str
    direction_delta: Decimal | None
    comparison_days: int
    components: list[dict[str, Any]]
    primary_opportunity: dict[str, Any] | None
    secondary_opportunity: dict[str, Any] | None
    opportunities: list[dict[str, Any]]
    target: dict[str, Any] | None
    latest: dict[str, Any] | None
    trend: dict[str, Any]
    notes: list[str]
    guidance: list[dict[str, str]]
    signals: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _target_payload(target: ProfileTarget | None) -> dict[str, Any] | None:
    if target is None:
        return None
    return {
        "id": str(target.id),
        "valid_from": target.valid_from.isoformat(),
        "valid_to": target.valid_to.isoformat() if target.valid_to else None,
        "weight_min": target.weight_min_kg,
        "weight_max": target.weight_max_kg,
        "fat_min": target.body_fat_min_percent,
        "fat_max": target.body_fat_max_percent,
        "muscle_min": target.muscle_min_percent,
        "muscle_max": target.muscle_max_percent,
    }


def effective_target_ranges(target: ProfileTarget | None) -> dict[str, Any]:
    """Prefer range fields; fall back to legacy single values as narrow bands."""
    if target is None:
        return {}
    weight_min = target.weight_min_kg
    weight_max = target.weight_max_kg
    if (weight_min is None or weight_max is None) and target.target_weight_kg is not None:
        weight_min = target.target_weight_kg - Decimal("0.50")
        weight_max = target.target_weight_kg + Decimal("0.50")
    fat_min = target.body_fat_min_percent
    fat_max = target.body_fat_max_percent
    if (fat_min is None or fat_max is None) and target.target_body_fat_percent is not None:
        fat_min = target.target_body_fat_percent - Decimal("0.50")
        fat_max = target.target_body_fat_percent + Decimal("0.50")
    muscle_min = target.muscle_min_percent
    muscle_max = target.muscle_max_percent
    if (muscle_min is None or muscle_max is None) and target.target_muscle_percent is not None:
        muscle_min = target.target_muscle_percent - Decimal("0.50")
        muscle_max = target.target_muscle_percent + Decimal("0.50")
    return {
        "weight_min": weight_min,
        "weight_max": weight_max,
        "fat_min": fat_min,
        "fat_max": fat_max,
        "muscle_min": muscle_min,
        "muscle_max": muscle_max,
    }


def _freshness(days_since: int | None) -> str:
    if days_since is None:
        return "stale"
    if days_since <= 14:
        return "fresh"
    if days_since <= 30:
        return "ageing"
    return "stale"


def _confidence(
    *,
    recent_count: int,
    days_since: int | None,
    has_fat: bool,
    has_muscle: bool,
    variability: float | None,
) -> str:
    if recent_count < 2 or days_since is None:
        return "Insufficient data"
    score = 0
    if recent_count >= 6:
        score += 2
    elif recent_count >= 3:
        score += 1
    if days_since <= 14:
        score += 2
    elif days_since <= 30:
        score += 1
    if has_fat:
        score += 1
    if has_muscle:
        score += 1
    if variability is not None and variability < 0.8:
        score += 1
    if score >= 6:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


def _opp_dict(opp: Opportunity | None) -> dict[str, Any] | None:
    if opp is None:
        return None
    return {
        "category": opp.category,
        "title": opp.title,
        "explanation": opp.explanation,
        "alignment_gain": float(opp.alignment_gain),
        "simulated_alignment": float(opp.simulated_alignment)
        if opp.simulated_alignment is not None
        else None,
    }


def evaluate_compass(
    profile: Profile,
    *,
    at=None,
    measurement: Measurement | None = None,
) -> CompassSnapshot:
    at = at or timezone.now()
    on_date = local_date(at, profile.timezone)
    target = target_for_date(profile, on_date)
    ranges = effective_target_ranges(target)
    algo = resolve_algorithm(profile)
    trend_days = algo.trend_window_days
    comparison_days = algo.comparison_window_days

    qs = measurement_queryset(profile).filter(measured_at__lte=at).order_by("-measured_at")
    latest = measurement or qs.first()
    notes: list[str] = []

    if latest is None:
        primary = _opp_dict(
            rank_opportunities(
                target=ranges,
                composition_available=False,
                algorithm=algo,
            )[0]
        )
        guidance = action_guidance(
            alignment=None,
            direction="Insufficient data",
            freshness="stale",
            confidence="Insufficient data",
            components=[],
            primary_opportunity=primary,
        )
        return CompassSnapshot(
            alignment=None,
            confidence="Insufficient data",
            freshness="stale",
            direction="Insufficient data",
            direction_delta=None,
            comparison_days=comparison_days,
            components=[],
            primary_opportunity=primary,
            secondary_opportunity=None,
            opportunities=[primary] if primary else [],
            target=_target_payload(target),
            latest=None,
            trend={},
            notes=["No measurements available."],
            guidance=guidance,
            signals=[],
        )

    if target is None or not any(ranges.values()):
        notes.append("Configure target ranges in Settings to unlock Target Alignment.")

    # Score/recommendations from smoothed recent position; fall back to latest when needed.
    def _current(attr: str, latest_val):
        trend_val = trend_average(profile, attr, end=at, days=trend_days)
        return trend_val if trend_val is not None else latest_val

    current_weight = _current("weight_kg", latest.weight_kg)
    current_fat = _current("body_fat_percent", latest.body_fat_percent)
    current_muscle = _current("muscle_percent", latest.muscle_percent)

    comps = component_scores(
        weight_kg=current_weight,
        body_fat_percent=current_fat,
        muscle_percent=current_muscle,
        algorithm=algo,
        **ranges,
    )
    alignment, _ = overall_alignment(comps, algorithm=algo)

    prior_end = latest.measured_at - timedelta(days=comparison_days)
    prior_weight = trend_average(
        profile, "weight_kg", end=prior_end, days=trend_days
    )
    prior_fat = trend_average(
        profile, "body_fat_percent", end=prior_end, days=trend_days
    )
    prior_muscle = trend_average(
        profile, "muscle_percent", end=prior_end, days=trend_days
    )
    prior_comps = component_scores(
        weight_kg=prior_weight,
        body_fat_percent=prior_fat,
        muscle_percent=prior_muscle,
        algorithm=algo,
        **ranges,
    )
    prior_alignment, _ = overall_alignment(prior_comps, algorithm=algo)
    direction_delta = None
    if alignment is not None and prior_alignment is not None:
        direction_delta = (alignment - prior_alignment).quantize(Decimal("0.01"))

    component_rows = []
    for row in components_to_dict(comps):
        key = row["key"]
        prior = prior_comps[key].score
        current = comps[key].score
        delta = None
        if prior is not None and current is not None:
            delta = (current - prior).quantize(Decimal("0.01"))
        row["direction"] = direction_label(delta)
        row["direction_delta"] = float(delta) if delta is not None else None
        component_rows.append(row)

    days_since = (timezone.localdate() - local_date(latest.measured_at, profile.timezone)).days
    recent_count = count_recent(profile, days=trend_days)
    variability = recent_variability(profile, "weight_kg", days=trend_days)
    has_fat = current_fat is not None
    has_muscle = current_muscle is not None
    composition_available = has_fat and has_muscle

    if recent_count < 3:
        notes.append("Trend guidance needs more recent measurements.")

    opportunities = rank_opportunities(
        weight_kg=current_weight,
        body_fat_percent=current_fat,
        muscle_percent=current_muscle,
        target=ranges,
        composition_available=composition_available,
        algorithm=algo,
    )
    primary = _opp_dict(opportunities[0] if opportunities else None)
    secondary = _opp_dict(opportunities[1] if len(opportunities) > 1 else None)
    opp_rows = [_opp_dict(o) for o in opportunities[:5]]
    opp_rows = [o for o in opp_rows if o is not None]
    confidence = _confidence(
        recent_count=recent_count,
        days_since=days_since,
        has_fat=has_fat,
        has_muscle=has_muscle,
        variability=variability,
    )
    freshness = _freshness(days_since)
    direction = direction_label(direction_delta)
    guidance = action_guidance(
        alignment=alignment,
        direction=direction,
        freshness=freshness,
        confidence=confidence,
        components=component_rows,
        primary_opportunity=primary,
    )
    signals = fitness_signals(
        height_cm=profile.height_cm,
        weight_kg=current_weight,
        body_fat_percent=current_fat,
        target=ranges,
    )

    trend = {
        "weight_kg": float(current_weight) if current_weight is not None else None,
        "body_fat_percent": float(current_fat) if current_fat is not None else None,
        "muscle_percent": float(current_muscle) if current_muscle is not None else None,
        "window_days": trend_days,
    }

    return CompassSnapshot(
        alignment=alignment,
        confidence=confidence,
        freshness=freshness,
        direction=direction,
        direction_delta=direction_delta,
        comparison_days=comparison_days,
        components=component_rows,
        primary_opportunity=primary,
        secondary_opportunity=secondary,
        opportunities=opp_rows,
        target=_target_payload(target),
        latest={
            "id": str(latest.id),
            "measured_at": latest.measured_at.isoformat(),
            "weight_kg": float(latest.weight_kg),
            "body_fat_percent": float(latest.body_fat_percent)
            if latest.body_fat_percent is not None
            else None,
            "muscle_percent": float(latest.muscle_percent)
            if latest.muscle_percent is not None
            else None,
            "days_since": days_since,
        },
        trend=trend,
        notes=notes,
        guidance=guidance,
        signals=signals,
    )
