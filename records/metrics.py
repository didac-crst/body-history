from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import fmean
from typing import Iterable
from zoneinfo import ZoneInfo

from django.db.models import QuerySet
from django.utils import timezone

from .models import Measurement, Profile, ProfileTarget


def to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def convert_fraction_to_percent(value) -> Decimal | None:
    """Convert Excel-style body-composition fractions (0.203) to percent (20.3)."""
    if value is None:
        return None
    number = Decimal(str(value))
    if number == 0:
        return None
    if 0 < number <= 1:
        return (number * Decimal("100")).quantize(Decimal("0.01"))
    return number.quantize(Decimal("0.01"))


def calculate_bmi(weight_kg, height_cm) -> Decimal | None:
    weight = to_decimal(weight_kg)
    height = to_decimal(height_cm)
    if weight is None or height is None or height <= 0:
        return None
    height_m = height / Decimal("100")
    return (weight / (height_m * height_m)).quantize(Decimal("0.01"))


def calculate_fat_mass_kg(weight_kg, body_fat_percent) -> Decimal | None:
    weight = to_decimal(weight_kg)
    fat = to_decimal(body_fat_percent)
    if weight is None or fat is None:
        return None
    return (weight * fat / Decimal("100")).quantize(Decimal("0.01"))


def target_for_date(profile: Profile, on_date: date) -> ProfileTarget | None:
    return (
        profile.targets.filter(valid_from__lte=on_date)
        .filter(models_q_valid_to(on_date))
        .order_by("-valid_from", "-created_at")
        .first()
    )


def models_q_valid_to(on_date: date):
    from django.db.models import Q

    return Q(valid_to__isnull=True) | Q(valid_to__gte=on_date)


def measurement_queryset(profile: Profile, include_excluded: bool | None = None) -> QuerySet:
    qs = profile.measurements.all()
    if include_excluded is None:
        include_excluded = profile.include_excluded_in_summaries
    if not include_excluded:
        qs = qs.filter(is_excluded=False)
    return qs


def enrich_measurement(measurement: Measurement, height_cm) -> dict:
    bmi = calculate_bmi(measurement.weight_kg, height_cm)
    fat_mass = calculate_fat_mass_kg(measurement.weight_kg, measurement.body_fat_percent)
    return {
        "measurement": measurement,
        "bmi": bmi,
        "fat_mass_kg": fat_mass,
        "year": timezone.localtime(measurement.measured_at).year,
    }


def local_date(dt: datetime, tz_name: str) -> date:
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, ZoneInfo(tz_name))
    return timezone.localtime(dt, ZoneInfo(tz_name)).date()


def same_local_date_exists(
    profile: Profile, measured_at: datetime, exclude_id=None
) -> bool:
    target = local_date(measured_at, profile.timezone)
    qs = profile.measurements.all()
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    for existing in qs.only("id", "measured_at"):
        if local_date(existing.measured_at, profile.timezone) == target:
            return True
    return False


def rolling_value_at(
    measurements: Iterable[Measurement],
    at: datetime,
    attr: str,
    window_days: int = 7,
) -> Decimal | None:
    """Average of values within +/- window around `at`, preferring nearest window before/at."""
    start = at - timedelta(days=window_days)
    values = []
    for m in measurements:
        if start <= m.measured_at <= at:
            value = getattr(m, attr)
            if value is not None:
                values.append(float(value))
    if not values:
        return None
    return Decimal(str(round(fmean(values), 2)))


def delta_for_period(
    profile: Profile,
    latest: Measurement,
    days: int,
    attr: str = "weight_kg",
) -> Decimal | None:
    qs = list(
        measurement_queryset(profile)
        .filter(measured_at__lte=latest.measured_at)
        .order_by("measured_at")
    )
    if not qs:
        return None
    current = getattr(latest, attr)
    if current is None:
        return None
    baseline_at = latest.measured_at - timedelta(days=days)
    baseline = rolling_value_at(qs, baseline_at, attr, window_days=max(3, days // 10))
    if baseline is None:
        # fall back to nearest earlier measurement at/before baseline
        earlier = [m for m in qs if m.measured_at <= baseline_at and getattr(m, attr) is not None]
        if not earlier:
            return None
        baseline = to_decimal(getattr(earlier[-1], attr))
    if baseline is None:
        return None
    return (to_decimal(current) - baseline).quantize(Decimal("0.01"))


def smooth_series(
    points: list[tuple[datetime, float]], window_days: int
) -> list[tuple[datetime, float]]:
    if not points or window_days <= 1:
        return points
    half = timedelta(days=window_days / 2)
    smoothed = []
    for ts, _ in points:
        window_vals = [
            value
            for other_ts, value in points
            if abs((other_ts - ts).total_seconds()) <= half.total_seconds()
        ]
        if window_vals:
            smoothed.append((ts, round(fmean(window_vals), 3)))
    return smoothed


def dashboard_metrics(profile: Profile) -> dict:
    qs = measurement_queryset(profile).order_by("-measured_at")
    latest = qs.first()
    if latest is None:
        return {"latest": None}

    enriched = enrich_measurement(latest, profile.height_cm)
    now = timezone.now()
    days_since = (now.date() - local_date(latest.measured_at, profile.timezone)).days

    def period_delta(days: int) -> dict:
        return {
            "weight_kg": delta_for_period(profile, latest, days, "weight_kg"),
            "body_fat_percent": delta_for_period(profile, latest, days, "body_fat_percent"),
            "muscle_percent": delta_for_period(profile, latest, days, "muscle_percent"),
        }

    target = target_for_date(profile, local_date(latest.measured_at, profile.timezone))
    return {
        "latest": latest,
        "bmi": enriched["bmi"],
        "fat_mass_kg": enriched["fat_mass_kg"],
        "days_since": days_since,
        "deltas": {
            "7d": period_delta(7),
            "30d": period_delta(30),
            "90d": period_delta(90),
            "365d": period_delta(365),
        },
        "target": target,
    }
