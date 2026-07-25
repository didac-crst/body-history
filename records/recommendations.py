"""Recommendation engine for Body Compass."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .scoring import component_scores, overall_alignment


STEP_WEIGHT = Decimal("0.5")
STEP_FAT = Decimal("0.5")
STEP_MUSCLE = Decimal("0.5")


@dataclass(frozen=True)
class Opportunity:
    category: str
    title: str
    explanation: str
    alignment_gain: Decimal
    simulated_alignment: Decimal | None


def _score_state(state: dict, target: dict) -> Decimal | None:
    comps = component_scores(
        weight_kg=state.get("weight_kg"),
        body_fat_percent=state.get("body_fat_percent"),
        muscle_percent=state.get("muscle_percent"),
        weight_min=target.get("weight_min"),
        weight_max=target.get("weight_max"),
        fat_min=target.get("fat_min"),
        fat_max=target.get("fat_max"),
        muscle_min=target.get("muscle_min"),
        muscle_max=target.get("muscle_max"),
    )
    score, _ = overall_alignment(comps)
    return score


def rank_opportunities(
    *,
    weight_kg=None,
    body_fat_percent=None,
    muscle_percent=None,
    target: dict,
    composition_available: bool,
) -> list[Opportunity]:
    base = {
        "weight_kg": weight_kg,
        "body_fat_percent": body_fat_percent,
        "muscle_percent": muscle_percent,
    }
    base_score = _score_state(base, target)
    if base_score is None:
        return [
            Opportunity(
                category="INSUFFICIENT_DATA",
                title="Need more data",
                explanation="Target alignment needs configured ranges and recent measurements.",
                alignment_gain=Decimal("0"),
                simulated_alignment=None,
            )
        ]

    if not composition_available:
        return [
            Opportunity(
                category="IMPROVE_MEASUREMENT_CONSISTENCY",
                title="Improve measurement consistency",
                explanation=(
                    "Body fat and muscle estimates are missing. "
                    "Trend guidance needs composition readings, not weight alone."
                ),
                alignment_gain=Decimal("0"),
                simulated_alignment=base_score,
            )
        ]

    candidates: list[tuple[str, str, str, dict]] = []
    if weight_kg is not None:
        candidates.append(
            (
                "REDUCE_WEIGHT",
                "Reduce weight carefully",
                "Lower weight by about 0.5 kg while watching composition.",
                {**base, "weight_kg": weight_kg - STEP_WEIGHT},
            )
        )
        candidates.append(
            (
                "GAIN_WEIGHT",
                "Gain weight carefully",
                "Raise weight by about 0.5 kg if composition stays favourable.",
                {**base, "weight_kg": weight_kg + STEP_WEIGHT},
            )
        )
    if body_fat_percent is not None:
        candidates.append(
            (
                "REDUCE_BODY_FAT",
                "Reduce body fat while preserving muscle",
                "This would currently improve alignment more than chasing weight alone.",
                {**base, "body_fat_percent": body_fat_percent - STEP_FAT},
            )
        )
    if muscle_percent is not None:
        candidates.append(
            (
                "BUILD_MUSCLE",
                "Build muscle",
                "Raising muscle percentage improves composition even if scale weight rises.",
                {
                    **base,
                    "muscle_percent": muscle_percent + STEP_MUSCLE,
                    "weight_kg": (weight_kg + STEP_WEIGHT) if weight_kg is not None else None,
                },
            )
        )

    scored: list[Opportunity] = []
    for category, title, explanation, state in candidates:
        # Reject weight-loss-only when it worsens composition framing:
        if category == "REDUCE_WEIGHT" and body_fat_percent is not None and muscle_percent is not None:
            # Prefer fat reduction over blind weight cut when fat is above target max.
            fat_max = target.get("fat_max")
            if fat_max is not None and body_fat_percent > fat_max:
                # still allow, but fat-reduction candidate should usually win on gain
                pass
        sim = _score_state(state, target)
        if sim is None:
            continue
        gain = (sim - base_score).quantize(Decimal("0.01"))
        # Reject scenarios that lower muscle score while only cutting weight.
        if category == "REDUCE_WEIGHT" and muscle_percent is not None:
            before = component_scores(
                weight_kg=weight_kg,
                body_fat_percent=body_fat_percent,
                muscle_percent=muscle_percent,
                weight_min=target.get("weight_min"),
                weight_max=target.get("weight_max"),
                fat_min=target.get("fat_min"),
                fat_max=target.get("fat_max"),
                muscle_min=target.get("muscle_min"),
                muscle_max=target.get("muscle_max"),
            )
            after = component_scores(
                weight_kg=state.get("weight_kg"),
                body_fat_percent=state.get("body_fat_percent"),
                muscle_percent=state.get("muscle_percent"),
                weight_min=target.get("weight_min"),
                weight_max=target.get("weight_max"),
                fat_min=target.get("fat_min"),
                fat_max=target.get("fat_max"),
                muscle_min=target.get("muscle_min"),
                muscle_max=target.get("muscle_max"),
            )
            if (
                before["body_fat"].score is not None
                and after["body_fat"].score is not None
                and after["body_fat"].score < before["body_fat"].score
                and gain <= 0
            ):
                continue
        scored.append(
            Opportunity(
                category=category,
                title=title,
                explanation=explanation,
                alignment_gain=gain,
                simulated_alignment=sim,
            )
        )

    scored.sort(key=lambda o: o.alignment_gain, reverse=True)
    positive = [o for o in scored if o.alignment_gain > 0]
    if not positive:
        return [
            Opportunity(
                category="MAINTAIN",
                title="Maintain",
                explanation="Current alignment is at or near target. No forced optimisation needed.",
                alignment_gain=Decimal("0"),
                simulated_alignment=base_score,
            )
        ]

    # Prefer composition opportunities over blind weight cuts when fat is high.
    fat_max = target.get("fat_max")
    if (
        body_fat_percent is not None
        and fat_max is not None
        and body_fat_percent > fat_max
    ):
        composition = [
            o for o in positive if o.category in {"REDUCE_BODY_FAT", "BUILD_MUSCLE"}
        ]
        if composition:
            return composition

    return positive
