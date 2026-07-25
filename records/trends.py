"""Trend helpers for Body Compass."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from statistics import fmean

from django.utils import timezone

from .metrics import measurement_queryset
from .models import Measurement, Profile


def _values(measurements: list[Measurement], attr: str) -> list[float]:
    out = []
    for m in measurements:
        value = getattr(m, attr)
        if value is not None:
            out.append(float(value))
    return out


def window_measurements(
    profile: Profile, *, end=None, days: int = 30
) -> list[Measurement]:
    end = end or timezone.now()
    start = end - timedelta(days=days)
    return list(
        measurement_queryset(profile)
        .filter(measured_at__gte=start, measured_at__lte=end)
        .order_by("measured_at")
    )


def trend_average(
    profile: Profile, attr: str, *, end=None, days: int = 30
) -> Decimal | None:
    values = _values(window_measurements(profile, end=end, days=days), attr)
    if not values:
        return None
    return Decimal(str(round(fmean(values), 2)))


def recent_variability(
    profile: Profile, attr: str = "weight_kg", *, days: int = 30
) -> float | None:
    values = _values(window_measurements(profile, days=days), attr)
    if len(values) < 3:
        return None
    mean = fmean(values)
    variance = fmean([(v - mean) ** 2 for v in values])
    return variance**0.5


def count_recent(profile: Profile, *, days: int = 30) -> int:
    return len(window_measurements(profile, days=days))
