"""Chart payloads for Body Compass decision charts (no radar)."""

from __future__ import annotations

from typing import Any

from .compass_history import alignment_history
from .models import Profile
from .preferences import resolve_algorithm
from .scoring import AlgorithmConfig
from .trends import trend_average


def _f(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _gap(value, lo, hi) -> tuple[float | None, str]:
    if value is None or lo is None or hi is None:
        return None, "unknown"
    v, a, b = float(value), float(lo), float(hi)
    if a <= v <= b:
        return 0.0, "aligned"
    if v < a:
        return round(v - a, 2), "below"
    return round(v - b, 2), "above"


def position_vs_target(
    profile: Profile,
    *,
    ranges: dict[str, Any],
    algorithm: AlgorithmConfig | None = None,
) -> list[dict[str, Any]]:
    """Horizontal range-bar data: trend value vs ideal (+ soft/hard context)."""
    algo = algorithm or resolve_algorithm(profile)
    days = algo.trend_window_days
    rows_spec = [
        (
            "weight",
            "Weight",
            "kg",
            trend_average(profile, "weight_kg", days=days),
            ranges.get("weight_min"),
            ranges.get("weight_max"),
            algo.weight_soft_kg,
            algo.weight_hard_kg,
        ),
        (
            "body_fat",
            "Body fat",
            "pp",
            trend_average(profile, "body_fat_percent", days=days),
            ranges.get("fat_min"),
            ranges.get("fat_max"),
            algo.fat_soft_pp,
            algo.fat_hard_pp,
        ),
        (
            "muscle",
            "Muscle",
            "pp",
            trend_average(profile, "muscle_percent", days=days),
            ranges.get("muscle_min"),
            ranges.get("muscle_max"),
            algo.muscle_soft_pp,
            algo.muscle_hard_pp,
        ),
    ]
    rows: list[dict[str, Any]] = []
    for key, label, gap_unit, value, lo, hi, soft, hard in rows_spec:
        if lo is None or hi is None:
            continue
        lo_f, hi_f = float(lo), float(hi)
        soft_f, hard_f = float(soft), float(hard)
        track_min = lo_f - hard_f
        track_max = hi_f + hard_f
        span = track_max - track_min or 1.0
        value_f = _f(value)
        gap, position = _gap(value, lo, hi)

        def pct(x: float) -> float:
            return max(0.0, min(100.0, ((x - track_min) / span) * 100.0))

        rows.append(
            {
                "key": key,
                "label": label,
                "unit": "kg" if key == "weight" else "%",
                "gap_unit": gap_unit,
                "value": value_f,
                "target_min": lo_f,
                "target_max": hi_f,
                "gap": gap,
                "position": position,
                "track_min": track_min,
                "track_max": track_max,
                "ideal_start_pct": pct(lo_f),
                "ideal_width_pct": max(1.0, pct(hi_f) - pct(lo_f)),
                "soft_start_pct": pct(lo_f - soft_f),
                "soft_width_pct": max(1.0, pct(hi_f + soft_f) - pct(lo_f - soft_f)),
                "marker_pct": pct(value_f) if value_f is not None else None,
                "window_days": days,
            }
        )
    return rows


def opportunity_impact(
    opportunities: list[dict[str, Any]] | None,
    *,
    current_alignment: float | None = None,
) -> dict[str, Any]:
    """Ranked impact bars from counterfactual opportunities.

    Track is absolute 0–100 alignment. Each bar marks the move from current
    alignment to simulated alignment (e.g. 36 → 39.94), not a bar from 0.
    """
    opps = opportunities or []
    if not opps:
        return {"available": False, "reason": "insufficient", "bars": []}
    if opps[0].get("category") in {"INSUFFICIENT_DATA", "IMPROVE_MEASUREMENT_CONSISTENCY"}:
        return {
            "available": False,
            "reason": opps[0].get("category", "insufficient").lower(),
            "bars": [],
            "message": opps[0].get("explanation") or opps[0].get("title"),
        }
    positive = [o for o in opps if (o.get("alignment_gain") or 0) > 0]
    if not positive:
        return {
            "available": False,
            "reason": "maintain",
            "bars": [],
            "message": opps[0].get("explanation") or "Near target — no forced optimisation.",
        }

    current = float(current_alignment) if current_alignment is not None else None
    bars = []
    for o in positive[:5]:
        gain = float(o["alignment_gain"])
        simulated = o.get("simulated_alignment")
        if simulated is not None:
            projected = float(simulated)
        elif current is not None:
            projected = min(100.0, current + gain)
        else:
            projected = gain

        if current is not None:
            start = max(0.0, min(100.0, current))
            end = max(0.0, min(100.0, projected))
            if end < start:
                start, end = end, start
            # Tiny gains still visible on the absolute scale.
            width = max(1.2, end - start)
            start_pct = start
        else:
            # No current score: fall back to gain plotted from 0.
            start_pct = 0.0
            width = max(1.2, min(100.0, gain))

        bars.append(
            {
                "title": o.get("title") or o.get("category"),
                "category": o.get("category"),
                "alignment_gain": gain,
                "current_alignment": current,
                "simulated_alignment": projected,
                "start_pct": round(start_pct, 2),
                "width_pct": round(min(100.0 - start_pct, width), 2),
            }
        )
    return {
        "available": True,
        "reason": None,
        "bars": bars,
        "message": None,
        "current_alignment": current,
    }


def alignment_sparkline(profile: Profile, *, days: int = 90, limit: int = 36) -> list[float]:
    """Recent overall alignment points for dashboard/mobile mini chart."""
    payload = alignment_history(profile, days=days, mode="today")
    points = payload.get("points") or []
    values = [float(p["alignment"]) for p in points if p.get("alignment") is not None]
    if len(values) > limit:
        values = values[-limit:]
    return values


def sparkline_polyline(
    values: list[float], *, width: float = 180, height: float = 40
) -> str | None:
    if len(values) < 2:
        return None
    vmin, vmax = min(values), max(values)
    span = (vmax - vmin) or 1.0
    parts = []
    for i, v in enumerate(values):
        x = (i / (len(values) - 1)) * width
        y = height - ((v - vmin) / span) * (height - 6) - 3
        parts.append(f"{x:.1f},{y:.1f}")
    return " ".join(parts)


def component_mini_bars(components: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    bars = []
    for c in components or []:
        score = c.get("score")
        bars.append(
            {
                "key": c.get("key"),
                "label": c.get("label"),
                "score": float(score) if score is not None else None,
                "direction": c.get("direction"),
            }
        )
    return bars
