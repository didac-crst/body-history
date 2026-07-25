"""Historical Target Alignment series for Compass charts."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal

from django.utils import timezone

from .compass import effective_target_ranges
from .guidance import action_guidance, fitness_signals
from .metrics import local_date, measurement_queryset, target_for_date
from .models import Profile
from .preferences import resolve_algorithm
from .scoring import AlgorithmConfig, component_scores, overall_alignment

TargetMode = Literal["historical", "today"]


def _score_point(measurement, ranges: dict[str, Any], algorithm: AlgorithmConfig) -> dict[str, Any] | None:
    if not ranges or not any(ranges.values()):
        return None
    comps = component_scores(
        weight_kg=measurement.weight_kg,
        body_fat_percent=measurement.body_fat_percent,
        muscle_percent=measurement.muscle_percent,
        algorithm=algorithm,
        **ranges,
    )
    alignment, _ = overall_alignment(comps, algorithm=algorithm)
    if alignment is None:
        return None
    return {
        "alignment": float(alignment),
        "weight": float(comps["weight"].score) if comps["weight"].score is not None else None,
        "body_fat": float(comps["body_fat"].score) if comps["body_fat"].score is not None else None,
        "muscle": float(comps["muscle"].score) if comps["muscle"].score is not None else None,
    }


def alignment_history(
    profile: Profile,
    *,
    days: int | None = 365,
    mode: TargetMode = "today",
) -> dict[str, Any]:
    """Score measurements over time.

    mode=today: recalculate every point against today's active target (default).
    mode=historical: use the ProfileTarget active on each measurement date.
    """
    algo = resolve_algorithm(profile)
    qs = measurement_queryset(profile).order_by("measured_at")
    if days is not None:
        qs = qs.filter(measured_at__gte=timezone.now() - timedelta(days=days))

    today = timezone.localdate()
    today_target = target_for_date(profile, today)
    today_ranges = effective_target_ranges(today_target)

    targets = list(profile.targets.order_by("valid_from", "created_at"))

    def ranges_for(on_date):
        if mode == "today":
            return today_ranges, str(today_target.id) if today_target else None
        active = None
        for target in targets:
            if target.valid_from > on_date:
                break
            if target.valid_to is None or target.valid_to >= on_date:
                active = target
        if active is None:
            return {}, None
        return effective_target_ranges(active), str(active.id)

    range_cache: dict[str, dict[str, Any]] = {}
    points: list[dict[str, Any]] = []
    for measurement in qs.iterator():
        on_date = local_date(measurement.measured_at, profile.timezone)
        ranges, target_id = ranges_for(on_date)
        if target_id and target_id not in range_cache:
            range_cache[target_id] = ranges
        if target_id:
            ranges = range_cache[target_id]
        scored = _score_point(measurement, ranges, algo)
        if scored is None:
            continue
        points.append(
            {
                "t": timezone.localtime(measurement.measured_at).isoformat(),
                "measurement_id": str(measurement.id),
                "target_id": target_id,
                **scored,
            }
        )

    return {
        "mode": mode,
        "days": days,
        "count": len(points),
        "points": points,
        "bands": {
            "weight_soft_kg": float(algo.weight_soft_kg),
            "weight_hard_kg": float(algo.weight_hard_kg),
            "fat_soft_pp": float(algo.fat_soft_pp),
            "fat_hard_pp": float(algo.fat_hard_pp),
            "muscle_soft_pp": float(algo.muscle_soft_pp),
            "muscle_hard_pp": float(algo.muscle_hard_pp),
        },
    }


def milestone_suggestions(
    *,
    weight_kg=None,
    body_fat_percent=None,
    muscle_percent=None,
    target: dict[str, Any],
    algorithm: AlgorithmConfig | None = None,
) -> list[dict[str, Any]]:
    """Near-term milestones toward soft bands / ideal ranges (not medical advice)."""
    algo = algorithm or AlgorithmConfig.defaults()
    comps = component_scores(
        weight_kg=weight_kg,
        body_fat_percent=body_fat_percent,
        muscle_percent=muscle_percent,
        weight_min=target.get("weight_min"),
        weight_max=target.get("weight_max"),
        fat_min=target.get("fat_min"),
        fat_max=target.get("fat_max"),
        muscle_min=target.get("muscle_min"),
        muscle_max=target.get("muscle_max"),
        algorithm=algo,
    )
    milestones: list[dict[str, Any]] = []

    def _add(category: str, title: str, detail: str, priority: Decimal):
        milestones.append(
            {
                "category": category,
                "title": title,
                "detail": detail,
                "priority": float(priority),
            }
        )

    fat = comps["body_fat"]
    if fat.available and fat.score is not None and fat.value is not None and fat.target_max is not None:
        soft_hi = fat.target_max + algo.fat_soft_pp
        hard_hi = fat.target_max + algo.fat_hard_pp
        if fat.value > hard_hi:
            _add(
                "FAT_SOFT_BAND",
                "Reach the fat soft band",
                f"Move body fat toward {soft_hi}% (soft upper) from {fat.value}%.",
                Decimal("100") - fat.score,
            )
        elif fat.value > soft_hi:
            _add(
                "FAT_IDEAL",
                "Enter the fat ideal range",
                f"Move body fat into {fat.target_min}–{fat.target_max}% from {fat.value}%.",
                Decimal("100") - fat.score,
            )
        elif fat.score < 100:
            _add(
                "FAT_IDEAL",
                "Settle inside the fat ideal range",
                f"Ideal fat band is {fat.target_min}–{fat.target_max}%.",
                Decimal("100") - fat.score,
            )

    muscle = comps["muscle"]
    if (
        muscle.available
        and muscle.score is not None
        and muscle.value is not None
        and muscle.target_min is not None
    ):
        soft_lo = muscle.target_min - algo.muscle_soft_pp
        if muscle.value < soft_lo:
            _add(
                "MUSCLE_SOFT_BAND",
                "Reach the muscle soft band",
                f"Raise muscle toward {soft_lo}% (soft lower) from {muscle.value}%.",
                Decimal("100") - muscle.score,
            )
        elif muscle.score < 100:
            _add(
                "MUSCLE_IDEAL",
                "Enter the muscle ideal range",
                f"Ideal muscle band is {muscle.target_min}–{muscle.target_max}%.",
                Decimal("100") - muscle.score,
            )

    weight = comps["weight"]
    if (
        weight.available
        and weight.score is not None
        and weight.value is not None
        and weight.target_max is not None
    ):
        soft_hi = weight.target_max + algo.weight_soft_kg
        if weight.value > soft_hi and weight.score < 100:
            _add(
                "WEIGHT_SOFT_BAND",
                "Reach the weight soft band",
                f"Move weight toward {soft_hi} kg (soft upper) from {weight.value} kg.",
                (Decimal("100") - weight.score) * Decimal("0.5"),
            )
        elif weight.score < 100:
            _add(
                "WEIGHT_IDEAL",
                "Enter the weight ideal range",
                f"Ideal weight band is {weight.target_min}–{weight.target_max} kg.",
                (Decimal("100") - weight.score) * Decimal("0.5"),
            )

    milestones.sort(key=lambda m: m["priority"], reverse=True)
    return milestones[:4]


def simulate_measurement(
    profile: Profile,
    *,
    weight_kg=None,
    body_fat_percent=None,
    muscle_percent=None,
    on_date=None,
) -> dict[str, Any]:
    """Score a hypothetical measurement against the active target."""
    from .recommendations import rank_opportunities

    algo = resolve_algorithm(profile)
    on_date = on_date or timezone.localdate()
    target = target_for_date(profile, on_date)
    ranges = effective_target_ranges(target)
    comps = component_scores(
        weight_kg=weight_kg,
        body_fat_percent=body_fat_percent,
        muscle_percent=muscle_percent,
        algorithm=algo,
        **ranges,
    )
    alignment, mass = overall_alignment(comps, algorithm=algo)
    composition_available = body_fat_percent is not None and muscle_percent is not None
    opportunities = rank_opportunities(
        weight_kg=weight_kg,
        body_fat_percent=body_fat_percent,
        muscle_percent=muscle_percent,
        target=ranges,
        composition_available=composition_available,
        algorithm=algo,
    )
    milestones = milestone_suggestions(
        weight_kg=weight_kg,
        body_fat_percent=body_fat_percent,
        muscle_percent=muscle_percent,
        target=ranges,
        algorithm=algo,
    )
    component_rows = [
        {
            "key": c.key,
            "label": c.label,
            "score": float(c.score) if c.score is not None else None,
            "value": float(c.value) if c.value is not None else None,
            "target_min": float(c.target_min) if c.target_min is not None else None,
            "target_max": float(c.target_max) if c.target_max is not None else None,
            "available": c.available,
        }
        for c in comps.values()
    ]
    opp_dicts = [
        {
            "category": o.category,
            "title": o.title,
            "explanation": o.explanation,
            "alignment_gain": float(o.alignment_gain),
            "simulated_alignment": float(o.simulated_alignment)
            if o.simulated_alignment is not None
            else None,
        }
        for o in opportunities[:3]
    ]
    guidance = action_guidance(
        alignment=alignment,
        direction="Stable",
        freshness="fresh",
        confidence="Medium",
        components=component_rows,
        primary_opportunity=opp_dicts[0] if opp_dicts else None,
    )
    signals = fitness_signals(
        height_cm=profile.height_cm,
        weight_kg=weight_kg,
        body_fat_percent=body_fat_percent,
        target=ranges,
    )
    return {
        "alignment": float(alignment) if alignment is not None else None,
        "weight_mass": float(mass),
        "components": component_rows,
        "opportunities": opp_dicts,
        "milestones": milestones,
        "guidance": guidance,
        "signals": signals,
        "target": {
            "valid_from": target.valid_from.isoformat() if target else None,
            "valid_to": target.valid_to.isoformat() if target and target.valid_to else None,
            **{k: float(v) if isinstance(v, Decimal) else v for k, v in ranges.items()},
        }
        if target
        else None,
    }
