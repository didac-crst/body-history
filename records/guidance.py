"""Action guidance and optional fitness signals for Body Compass."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .metrics import calculate_bmi, calculate_fat_mass_kg


def action_guidance(
    *,
    alignment: Decimal | None,
    direction: str,
    freshness: str,
    confidence: str,
    components: list[dict[str, Any]],
    primary_opportunity: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Short, non-medical next-step copy derived from the current snapshot."""
    items: list[dict[str, str]] = []

    if alignment is None:
        return [
            {
                "title": "Set destination and measure",
                "body": "Configure target ranges and add a recent measurement to unlock alignment guidance.",
            }
        ]

    if freshness == "stale":
        items.append(
            {
                "title": "Refresh the reading",
                "body": "Latest data is stale. A consistent morning measurement improves confidence before chasing changes.",
            }
        )
    elif confidence in {"Low", "Insufficient data"}:
        items.append(
            {
                "title": "Build a short trend",
                "body": "A few more composition readings over the next 2–3 weeks will make direction more trustworthy.",
            }
        )

    fat = next((c for c in components if c.get("key") == "body_fat"), None)
    muscle = next((c for c in components if c.get("key") == "muscle"), None)
    weight = next((c for c in components if c.get("key") == "weight"), None)

    if primary_opportunity and primary_opportunity.get("category") == "MAINTAIN":
        items.append(
            {
                "title": "Maintain",
                "body": "Alignment is near target. Hold the pattern that got you here rather than forcing further optimisation.",
            }
        )
    elif primary_opportunity and primary_opportunity.get("category") == "REDUCE_BODY_FAT":
        items.append(
            {
                "title": "Prioritise fat loss with muscle preserved",
                "body": (
                    f"{primary_opportunity.get('explanation', '')} "
                    "Avoid aggressive weight cuts that also drop muscle score."
                ).strip(),
            }
        )
    elif primary_opportunity and primary_opportunity.get("category") == "BUILD_MUSCLE":
        items.append(
            {
                "title": "Build muscle even if scale weight rises",
                "body": primary_opportunity.get(
                    "explanation",
                    "Raising muscle percentage improves composition alignment.",
                ),
            }
        )
    elif primary_opportunity and primary_opportunity.get("category") == "IMPROVE_MEASUREMENT_CONSISTENCY":
        items.append(
            {
                "title": "Include composition when you weigh",
                "body": "Weight alone cannot steer body-composition direction. Add fat and muscle estimates when available.",
            }
        )
    elif primary_opportunity:
        items.append(
            {
                "title": primary_opportunity.get("title") or "Primary direction",
                "body": primary_opportunity.get("explanation") or "Follow the ranked opportunity with the best alignment gain.",
            }
        )

    if (
        fat
        and muscle
        and fat.get("score") is not None
        and muscle.get("score") is not None
        and fat["score"] < 50
        and muscle["score"] < 50
        and weight
        and weight.get("score") is not None
        and weight["score"] > fat["score"]
    ):
        items.append(
            {
                "title": "Composition over scale weight",
                "body": "Weight looks closer to target than fat/muscle. Favour recomposition signals over chasing the scale alone.",
            }
        )

    if direction == "Improving":
        items.append(
            {
                "title": "Keep the current trajectory",
                "body": "Overall alignment is improving versus the prior period. Stay consistent rather than changing everything at once.",
            }
        )
    elif direction == "Drifting away":
        items.append(
            {
                "title": "Arrest the drift",
                "body": "Alignment has declined versus the prior period. Focus on the primary opportunity before adding new goals.",
            }
        )

    # De-dupe by title while preserving order.
    seen = set()
    unique = []
    for item in items:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        unique.append(item)
    return unique[:4]


def fitness_signals(
    *,
    height_cm,
    weight_kg=None,
    body_fat_percent=None,
    target: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Optional derived context (BMI / fat mass). Not scored as medical status."""
    signals: list[dict[str, Any]] = []
    bmi = calculate_bmi(weight_kg, height_cm) if weight_kg is not None else None
    if bmi is not None:
        signals.append(
            {
                "key": "bmi",
                "label": "BMI (derived)",
                "value": float(bmi),
                "unit": "",
                "note": "Derived from weight and height; not a Compass score component.",
            }
        )

    fat_mass = (
        calculate_fat_mass_kg(weight_kg, body_fat_percent)
        if weight_kg is not None and body_fat_percent is not None
        else None
    )
    if fat_mass is not None:
        signals.append(
            {
                "key": "fat_mass_kg",
                "label": "Fat mass (estimate)",
                "value": float(fat_mass),
                "unit": "kg",
                "note": "Consumer-scale estimate from weight × body-fat %.",
            }
        )

    if target and weight_kg is not None:
        w_min = target.get("weight_min")
        w_max = target.get("weight_max")
        f_min = target.get("fat_min")
        f_max = target.get("fat_max")
        if w_min is not None and w_max is not None and f_min is not None and f_max is not None:
            lo = calculate_fat_mass_kg(w_min, f_min)
            hi = calculate_fat_mass_kg(w_max, f_max)
            if lo is not None and hi is not None:
                signals.append(
                    {
                        "key": "target_fat_mass_band",
                        "label": "Target fat-mass band",
                        "value": f"{float(lo):.2f}–{float(hi):.2f}",
                        "unit": "kg",
                        "note": "Implied by active weight and body-fat target ranges.",
                    }
                )
        if w_min is not None and w_max is not None and height_cm is not None:
            bmi_lo = calculate_bmi(w_min, height_cm)
            bmi_hi = calculate_bmi(w_max, height_cm)
            if bmi_lo is not None and bmi_hi is not None:
                signals.append(
                    {
                        "key": "target_bmi_band",
                        "label": "Target BMI band",
                        "value": f"{float(bmi_lo):.2f}–{float(bmi_hi):.2f}",
                        "unit": "",
                        "note": "Implied by active weight target and profile height.",
                    }
                )

    return signals
