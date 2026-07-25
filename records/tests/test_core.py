from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone

from records.importer import import_workbook, parse_workbook, report_to_dict
from records.metrics import (
    calculate_bmi,
    calculate_fat_mass_kg,
    convert_fraction_to_percent,
    dashboard_metrics,
    same_local_date_exists,
    target_for_date,
)
from records.models import Measurement, Profile, ProfileTarget


pytestmark = pytest.mark.django_db


@pytest.fixture
def profile():
    return Profile.objects.create(
        display_name="Test",
        height_cm=Decimal("181.00"),
        timezone="Europe/Paris",
    )


def test_bmi_calculation():
    assert calculate_bmi(Decimal("81.45"), Decimal("181")) == Decimal("24.86")


def test_fat_mass_calculation():
    assert calculate_fat_mass_kg(Decimal("80"), Decimal("20.3")) == Decimal("16.24")


def test_percent_fraction_conversion_from_excel():
    assert convert_fraction_to_percent(Decimal("0.203")) == Decimal("20.30")
    assert convert_fraction_to_percent(Decimal("20.3")) == Decimal("20.30")
    assert convert_fraction_to_percent(0) is None


def test_duplicate_date_warning_helper(profile):
    now = timezone.now()
    Measurement.objects.create(
        profile=profile,
        measured_at=now,
        weight_kg=Decimal("75.00"),
        source=Measurement.SOURCE_MANUAL,
    )
    assert same_local_date_exists(profile, now) is True
    assert same_local_date_exists(profile, now + timedelta(days=1)) is False


def test_multiple_measurements_same_day_allowed(profile):
    day = timezone.make_aware(datetime(2024, 5, 1, 8, 0))
    Measurement.objects.create(
        profile=profile, measured_at=day, weight_kg=Decimal("74.00")
    )
    Measurement.objects.create(
        profile=profile,
        measured_at=day + timedelta(hours=4),
        weight_kg=Decimal("74.20"),
    )
    assert profile.measurements.count() == 2


def test_target_version_lookup_by_date(profile):
    ProfileTarget.objects.create(
        profile=profile,
        valid_from=date(2010, 1, 1),
        valid_to=date(2019, 12, 31),
        target_bmi=Decimal("23.00"),
    )
    ProfileTarget.objects.create(
        profile=profile,
        valid_from=date(2020, 1, 1),
        target_bmi=Decimal("22.00"),
        target_body_fat_percent=Decimal("17.00"),
        target_muscle_percent=Decimal("39.80"),
    )
    assert target_for_date(profile, date(2015, 6, 1)).target_bmi == Decimal("23.00")
    assert target_for_date(profile, date(2024, 6, 1)).target_bmi == Decimal("22.00")
    assert target_for_date(profile, date(2008, 1, 1)) is None


def test_excluded_measurements_omitted_from_default_summaries(profile):
    latest = timezone.now()
    Measurement.objects.create(
        profile=profile,
        measured_at=latest - timedelta(days=2),
        weight_kg=Decimal("80.00"),
    )
    Measurement.objects.create(
        profile=profile,
        measured_at=latest,
        weight_kg=Decimal("90.00"),
        is_excluded=True,
        exclusion_reason="spike",
    )
    metrics = dashboard_metrics(profile)
    assert metrics["latest"].weight_kg == Decimal("80.00")


def _sample_workbook(tmp_path: Path) -> Path:
    from openpyxl import Workbook

    path = tmp_path / "sample.xlsx"
    wb = Workbook()
    # Keep a decoy sheet and the General source sheet.
    ws0 = wb.active
    ws0.title = "Notes"
    ws0["A1"] = "ignore"
    ws = wb.create_sheet("General")
    ws.append(
        [
            "Data",
            "Pes",
            "% Grassa",
            "Grassa",
            "IMC",
            "Alçada",
            "% Muscul",
            "Nota Pes",
            "Nota Grassa",
            "Nota Muscul",
            "Nota Total",
            "Outlier?",
            "Year",
        ]
    )
    ws.append(
        [
            datetime(2020, 1, 1),
            75.5,
            0.203,
            "=B2*C2",
            "=B2/(F2)^2",
            1.81,
            0.398,
            "=1",
            "=1",
            "=1",
            "=1",
            0,
            "=YEAR(A2)",
        ]
    )
    ws.append(
        [
            datetime(2020, 1, 8),
            76.0,
            0.21,
            "=B3*C3",
            "=B3/(F3)^2",
            1.81,
            0.39,
            "=1",
            "=1",
            "=1",
            "=1",
            0,
            "=YEAR(A3)",
        ]
    )
    ws.append(
        [
            None,
            "bad",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
    )
    wb.save(path)
    return path


def test_import_dry_run_and_formula_handling(tmp_path, profile):
    path = _sample_workbook(tmp_path)
    report = parse_workbook(path)
    data = report_to_dict(report)
    assert data["candidate_count"] == 3
    assert data["accepted_count"] == 2
    assert data["rejected_count"] == 1
    assert data["date_range"]["first"] == "2020-01-01"
    assert data["date_range"]["last"] == "2020-01-08"
    assert "IMC" in data["formulas_ignored"]
    assert "Grassa" in data["formulas_ignored"]
    accepted = [r for r in report.rows if r.ok]
    assert accepted[0].body_fat_percent == Decimal("20.30")
    assert accepted[0].muscle_percent == Decimal("39.80")


def test_importer_records_invalid_rows_and_is_idempotent(tmp_path, profile):
    path = _sample_workbook(tmp_path)
    batch1 = import_workbook(profile, path)
    assert batch1.accepted_count == 2
    assert batch1.rejected_count == 1
    assert profile.measurements.count() == 2
    assert batch1.rows.filter(status="rejected").count() == 1

    batch2 = import_workbook(profile, path)
    assert batch2.id == batch1.id
    assert profile.measurements.count() == 2


def test_csv_export_includes_derived_metrics(client, django_user_model, profile):
    user = django_user_model.objects.create_user(username="u", password="pass")
    client.force_login(user)
    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("80.00"),
        body_fat_percent=Decimal("20.00"),
        muscle_percent=Decimal("40.00"),
    )
    response = client.get("/history/export.csv")
    assert response.status_code == 200
    body = response.content.decode()
    assert "bmi" in body.splitlines()[0]
    assert "fat_mass_kg" in body.splitlines()[0]
    assert "24.42" in body  # 80 / (1.81^2)
    assert "16.00" in body
