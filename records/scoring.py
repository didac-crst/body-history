"""Range-based Body Compass scoring (algorithm defaults only; no personal targets)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


# Algorithm defaults — not personal target values.
WEIGHT_IMPORTANCE = Decimal("0.25")
BODY_FAT_IMPORTANCE = Decimal("0.45")
MUSCLE_IMPORTANCE = Decimal("0.30")

WEIGHT_SOFT_KG = Decimal("1.00")
WEIGHT_HARD_KG = Decimal("3.00")
FAT_SOFT_PP = Decimal("1.00")
FAT_HARD_PP = Decimal("3.00")
MUSCLE_SOFT_PP = Decimal("1.00")
MUSCLE_HARD_PP = Decimal("3.00")

TREND_WINDOW_DAYS = 30
COMPARISON_WINDOW_DAYS = 30
DIRECTION_THRESHOLD = Decimal("2")


def _d(value) -> Decimal:
    return Decimal(str(value))


def score_against_range(
    value,
    ideal_min,
    ideal_max,
    lower_soft,
    lower_hard,
    upper_soft,
    upper_hard,
) -> Decimal | None:
    """Score 0-100 against an ideal range with soft/hard outer bands."""
    if value is None or ideal_min is None or ideal_max is None:
        return None
    v = _d(value)
    lo = _d(ideal_min)
    hi = _d(ideal_max)
    if lo > hi:
        lo, hi = hi, lo
    if lo <= v <= hi:
        return Decimal("100")

    if v < lo:
        soft = lo - _d(lower_soft)
        hard = lo - _d(lower_hard)
        if v >= soft:
            # soft..ideal_min maps 70..100
            span = lo - soft
            if span <= 0:
                return Decimal("70")
            return (Decimal("70") + (Decimal("30") * (v - soft) / span)).quantize(
                Decimal("0.01")
            )
        if v >= hard:
            # hard..soft maps 0..70
            span = soft - hard
            if span <= 0:
                return Decimal("0")
            return (Decimal("70") * (v - hard) / span).quantize(Decimal("0.01"))
        return Decimal("0")

    # v > hi
    soft = hi + _d(upper_soft)
    hard = hi + _d(upper_hard)
    if v <= soft:
        span = soft - hi
        if span <= 0:
            return Decimal("70")
        return (Decimal("100") - (Decimal("30") * (v - hi) / span)).quantize(
            Decimal("0.01")
        )
    if v <= hard:
        span = hard - soft
        if span <= 0:
            return Decimal("0")
        return (Decimal("70") * (hard - v) / span).quantize(Decimal("0.01"))
    return Decimal("0")


@dataclass(frozen=True)
class ComponentScore:
    key: str
    label: str
    score: Decimal | None
    value: Decimal | None
    target_min: Decimal | None
    target_max: Decimal | None
    available: bool


def component_scores(
    *,
    weight_kg=None,
    body_fat_percent=None,
    muscle_percent=None,
    weight_min=None,
    weight_max=None,
    fat_min=None,
    fat_max=None,
    muscle_min=None,
    muscle_max=None,
) -> dict[str, ComponentScore]:
    return {
        "weight": ComponentScore(
            key="weight",
            label="Weight",
            score=score_against_range(
                weight_kg,
                weight_min,
                weight_max,
                WEIGHT_SOFT_KG,
                WEIGHT_HARD_KG,
                WEIGHT_SOFT_KG,
                WEIGHT_HARD_KG,
            ),
            value=_d(weight_kg) if weight_kg is not None else None,
            target_min=_d(weight_min) if weight_min is not None else None,
            target_max=_d(weight_max) if weight_max is not None else None,
            available=weight_kg is not None and weight_min is not None and weight_max is not None,
        ),
        "body_fat": ComponentScore(
            key="body_fat",
            label="Body fat",
            score=score_against_range(
                body_fat_percent,
                fat_min,
                fat_max,
                FAT_SOFT_PP,
                FAT_HARD_PP,
                FAT_SOFT_PP,
                FAT_HARD_PP,
            ),
            value=_d(body_fat_percent) if body_fat_percent is not None else None,
            target_min=_d(fat_min) if fat_min is not None else None,
            target_max=_d(fat_max) if fat_max is not None else None,
            available=body_fat_percent is not None
            and fat_min is not None
            and fat_max is not None,
        ),
        "muscle": ComponentScore(
            key="muscle",
            label="Muscle",
            score=score_against_range(
                muscle_percent,
                muscle_min,
                muscle_max,
                MUSCLE_SOFT_PP,
                MUSCLE_HARD_PP,
                MUSCLE_SOFT_PP,
                MUSCLE_HARD_PP,
            ),
            value=_d(muscle_percent) if muscle_percent is not None else None,
            target_min=_d(muscle_min) if muscle_min is not None else None,
            target_max=_d(muscle_max) if muscle_max is not None else None,
            available=muscle_percent is not None
            and muscle_min is not None
            and muscle_max is not None,
        ),
    }


def overall_alignment(components: dict[str, ComponentScore]) -> tuple[Decimal | None, Decimal]:
    """Return (score, weight_mass_used) using available components only."""
    weights = {
        "weight": WEIGHT_IMPORTANCE,
        "body_fat": BODY_FAT_IMPORTANCE,
        "muscle": MUSCLE_IMPORTANCE,
    }
    total_w = Decimal("0")
    total = Decimal("0")
    for key, weight in weights.items():
        comp = components[key]
        if comp.available and comp.score is not None:
            total += comp.score * weight
            total_w += weight
    if total_w <= 0:
        return None, Decimal("0")
    return (total / total_w).quantize(Decimal("0.01")), total_w


def direction_label(delta: Decimal | None) -> str:
    if delta is None:
        return "Insufficient data"
    if delta > DIRECTION_THRESHOLD:
        return "Improving"
    if delta < -DIRECTION_THRESHOLD:
        return "Drifting away"
    return "Stable"


def components_to_dict(components: dict[str, ComponentScore]) -> list[dict[str, Any]]:
    rows = []
    for comp in components.values():
        rows.append(
            {
                "key": comp.key,
                "label": comp.label,
                "score": float(comp.score) if comp.score is not None else None,
                "value": float(comp.value) if comp.value is not None else None,
                "target_min": float(comp.target_min) if comp.target_min is not None else None,
                "target_max": float(comp.target_max) if comp.target_max is not None else None,
                "available": comp.available,
            }
        )
    return rows
