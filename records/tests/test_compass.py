from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from records.compass import evaluate_compass
from records.metrics import target_for_date
from records.models import Measurement, Profile, ProfileTarget
from records.recommendations import rank_opportunities
from records.scoring import (
    WEIGHT_IMPORTANCE,
    component_scores,
    direction_label,
    overall_alignment,
    score_against_range,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def profile():
    return Profile.objects.create(
        display_name="Test",
        height_cm=Decimal("181.00"),
        timezone="Europe/Paris",
    )


@pytest.fixture
def target(profile):
    return ProfileTarget.objects.create(
        profile=profile,
        valid_from=date(2020, 1, 1),
        weight_min_kg=Decimal("72.00"),
        weight_max_kg=Decimal("73.00"),
        body_fat_min_percent=Decimal("15.00"),
        body_fat_max_percent=Decimal("16.50"),
        muscle_min_percent=Decimal("38.00"),
        muscle_max_percent=Decimal("39.00"),
    )


def test_inside_range_score():
    assert score_against_range(72.5, 72, 73, 1, 3, 1, 3) == Decimal("100")


def test_upper_and_lower_deviations():
    upper = score_against_range(74, 72, 73, 1, 3, 1, 3)
    lower = score_against_range(71, 72, 73, 1, 3, 1, 3)
    assert upper is not None and upper < 100
    assert lower is not None and lower < 100


def test_asymmetric_tolerances():
    mild = score_against_range(74, 72, 73, 1, 5, 1, 2)
    harsh = score_against_range(74, 72, 73, 1, 5, 0.5, 1)
    assert mild > harsh


def test_missing_metrics_not_zero(target):
    comps = component_scores(
        weight_kg=Decimal("72.5"),
        body_fat_percent=None,
        muscle_percent=None,
        weight_min=target.weight_min_kg,
        weight_max=target.weight_max_kg,
        fat_min=target.body_fat_min_percent,
        fat_max=target.body_fat_max_percent,
        muscle_min=target.muscle_min_percent,
        muscle_max=target.muscle_max_percent,
    )
    score, mass = overall_alignment(comps)
    assert score == Decimal("100")
    assert mass == WEIGHT_IMPORTANCE
    assert comps["body_fat"].score is None


def test_all_metrics_missing(target):
    comps = component_scores(
        weight_min=target.weight_min_kg,
        weight_max=target.weight_max_kg,
        fat_min=target.body_fat_min_percent,
        fat_max=target.body_fat_max_percent,
        muscle_min=target.muscle_min_percent,
        muscle_max=target.muscle_max_percent,
    )
    score, mass = overall_alignment(comps)
    assert score is None
    assert mass == 0


def test_target_version_selection(profile):
    ProfileTarget.objects.create(
        profile=profile,
        valid_from=date(2010, 1, 1),
        valid_to=date(2019, 12, 31),
        weight_min_kg=Decimal("74.00"),
        weight_max_kg=Decimal("76.00"),
    )
    ProfileTarget.objects.create(
        profile=profile,
        valid_from=date(2020, 1, 1),
        weight_min_kg=Decimal("72.00"),
        weight_max_kg=Decimal("73.00"),
    )
    assert target_for_date(profile, date(2015, 6, 1)).weight_min_kg == Decimal("74.00")
    assert target_for_date(profile, date(2024, 6, 1)).weight_min_kg == Decimal("72.00")


def test_direction_labels():
    assert direction_label(Decimal("3")) == "Improving"
    assert direction_label(Decimal("0")) == "Stable"
    assert direction_label(Decimal("-3")) == "Drifting away"


def test_counterfactual_ranking_prefers_fat_cut(target):
    opps = rank_opportunities(
        weight_kg=Decimal("75.0"),
        body_fat_percent=Decimal("20.0"),
        muscle_percent=Decimal("35.0"),
        target={
            "weight_min": target.weight_min_kg,
            "weight_max": target.weight_max_kg,
            "fat_min": target.body_fat_min_percent,
            "fat_max": target.body_fat_max_percent,
            "muscle_min": target.muscle_min_percent,
            "muscle_max": target.muscle_max_percent,
        },
        composition_available=True,
    )
    assert opps[0].category in {"REDUCE_BODY_FAT", "BUILD_MUSCLE"}


def test_maintain_when_inside(target):
    opps = rank_opportunities(
        weight_kg=Decimal("72.5"),
        body_fat_percent=Decimal("15.5"),
        muscle_percent=Decimal("38.5"),
        target={
            "weight_min": target.weight_min_kg,
            "weight_max": target.weight_max_kg,
            "fat_min": target.body_fat_min_percent,
            "fat_max": target.body_fat_max_percent,
            "muscle_min": target.muscle_min_percent,
            "muscle_max": target.muscle_max_percent,
        },
        composition_available=True,
    )
    assert opps[0].category == "MAINTAIN"


def test_weight_only_recommends_consistency(target):
    opps = rank_opportunities(
        weight_kg=Decimal("75.0"),
        body_fat_percent=None,
        muscle_percent=None,
        target={
            "weight_min": target.weight_min_kg,
            "weight_max": target.weight_max_kg,
            "fat_min": target.body_fat_min_percent,
            "fat_max": target.body_fat_max_percent,
            "muscle_min": target.muscle_min_percent,
            "muscle_max": target.muscle_max_percent,
        },
        composition_available=False,
    )
    assert opps[0].category == "IMPROVE_MEASUREMENT_CONSISTENCY"


def test_score_cap_at_100():
    assert score_against_range(72.5, 72, 73, 1, 3, 1, 3) <= 100


def test_personal_targets_loaded_from_db_not_constants(profile, target):
    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("72.50"),
        body_fat_percent=Decimal("15.50"),
        muscle_percent=Decimal("38.50"),
    )
    snap = evaluate_compass(profile)
    assert snap.target is not None
    assert snap.target["weight_min"] == Decimal("72.00")
    # Ensure scoring module does not embed these personal numbers.
    import records.scoring as scoring

    source = open(scoring.__file__).read()
    assert "72.5" not in source
    assert "72.00" not in source


def test_compass_post_save_full_data(client, django_user_model, profile, target):
    user = django_user_model.objects.create_user(username="u", password="pass")
    client.force_login(user)
    # prior points for trend
    now = timezone.now()
    for i in range(5):
        Measurement.objects.create(
            profile=profile,
            measured_at=now - timedelta(days=i + 1),
            weight_kg=Decimal("75.50"),
            body_fat_percent=Decimal("20.00"),
            muscle_percent=Decimal("35.00"),
        )
    response = client.post(
        "/manual_import/",
        {
            "weight_kg": "75.2",
            "body_fat_percent": "20.3",
            "muscle_percent": "35.3",
            "measured_on": timezone.localdate().isoformat(),
        },
    )
    assert response.status_code == 200
    assert b"Target Alignment" in response.content
    assert b"Primary opportunity" in response.content


def test_compass_post_save_weight_only(client, django_user_model, profile, target):
    user = django_user_model.objects.create_user(username="u2", password="pass")
    client.force_login(user)
    response = client.post(
        "/manual_import/",
        {
            "weight_kg": "75.2",
            "body_fat_percent": "",
            "muscle_percent": "",
            "measured_on": timezone.localdate().isoformat(),
        },
    )
    assert response.status_code == 200
    assert b"Improve measurement consistency" in response.content or b"consistency" in response.content.lower()
