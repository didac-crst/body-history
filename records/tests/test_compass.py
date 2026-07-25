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


def test_wider_fat_muscle_defaults_avoid_zero_floor(target):
    """Fat/muscle soft-hard bands keep typical off-target readings scorable."""
    comps = component_scores(
        weight_kg=Decimal("75.20"),
        body_fat_percent=Decimal("20.30"),
        muscle_percent=Decimal("35.40"),
        weight_min=target.weight_min_kg,
        weight_max=target.weight_max_kg,
        fat_min=target.body_fat_min_percent,
        fat_max=target.body_fat_max_percent,
        muscle_min=target.muscle_min_percent,
        muscle_max=target.muscle_max_percent,
    )
    assert comps["body_fat"].score == Decimal("38.50")
    assert comps["muscle"].score == Decimal("39.20")
    assert comps["weight"].score == Decimal("28.00")
    score, _ = overall_alignment(comps)
    assert score == Decimal("36.08")


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


def test_compass_post_save_full_data(client, user, profile, target):
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


def test_compass_post_save_weight_only(client, user, profile, target):
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


def test_alignment_history_modes(profile, target):
    from records.compass_history import alignment_history

    now = timezone.now()
    Measurement.objects.create(
        profile=profile,
        measured_at=now - timedelta(days=10),
        weight_kg=Decimal("75.00"),
        body_fat_percent=Decimal("20.00"),
        muscle_percent=Decimal("35.00"),
    )
    ProfileTarget.objects.create(
        profile=profile,
        valid_from=date(2005, 1, 1),
        valid_to=date(2019, 12, 31),
        body_fat_min_percent=Decimal("18.00"),
        body_fat_max_percent=Decimal("19.00"),
        muscle_min_percent=Decimal("36.00"),
        muscle_max_percent=Decimal("37.00"),
    )
    hist = alignment_history(profile, days=30, mode="historical")
    today = alignment_history(profile, days=30, mode="today")
    assert hist["count"] >= 1
    assert today["count"] >= 1
    assert hist["points"][0]["alignment"] is not None


def test_simulate_measurement_returns_opportunities(profile, target):
    from records.compass_history import simulate_measurement

    result = simulate_measurement(
        profile,
        weight_kg=Decimal("75.20"),
        body_fat_percent=Decimal("20.30"),
        muscle_percent=Decimal("35.40"),
    )
    assert result["alignment"] is not None
    assert result["opportunities"]
    assert result["milestones"]


def test_compass_history_api(client, user, profile, target):
    client.force_login(user)
    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("75.00"),
        body_fat_percent=Decimal("20.00"),
        muscle_percent=Decimal("35.00"),
    )
    response = client.get("/api/compass-history/?range=90d&mode=today")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "today"
    assert payload["count"] >= 1


def test_compass_simulate_api(client, user, profile, target):
    client.force_login(user)
    response = client.get(
        "/api/compass-simulate/?weight_kg=75.2&body_fat_percent=20.3&muscle_percent=35.4"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["alignment"] is not None
    assert "opportunities" in payload


def test_compass_page_includes_chart_and_simulator(client, user, profile, target):
    client.force_login(user)
    response = client.get("/compass/")
    assert response.status_code == 200
    assert b"Alignment history" in response.content
    assert b"Opportunity simulator" in response.content
    assert b"compass.js" in response.content
    assert b"Guidance" in response.content or b"Fitness signals" in response.content


def test_user_cannot_access_other_users_compass_data(
    client, user, profile, target, django_user_model
):
    client.force_login(user)
    other_user = django_user_model.objects.create_user(username="partner", password="pass")
    Profile.objects.create(
        user=other_user,
        display_name="Partner",
        height_cm=Decimal("165.00"),
        timezone="Europe/Paris",
    )
    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("75.00"),
        body_fat_percent=Decimal("20.00"),
        muscle_percent=Decimal("35.00"),
    )
    assert client.post(
        "/settings/switch-profile/",
        {"profile_id": str(other_user.body_profile.id), "next": "/compass/"},
    ).status_code == 404
    compass = client.get("/compass/")
    assert compass.status_code == 200
    assert b"75" in compass.content


def test_post_save_includes_alignment_delta(client, user, profile, target):
    client.force_login(user)
    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now() - timedelta(days=3),
        weight_kg=Decimal("76.00"),
        body_fat_percent=Decimal("21.00"),
        muscle_percent=Decimal("34.50"),
    )
    response = client.post(
        "/manual_import/",
        {
            "weight_kg": "75.2",
            "body_fat_percent": "20.3",
            "muscle_percent": "35.4",
            "measured_on": timezone.localdate().isoformat(),
        },
    )
    assert response.status_code == 200
    assert b"Target Alignment" in response.content
    assert b"vs previous" in response.content


def test_settings_shows_profile_and_preview(client, user, profile, target):
    client.force_login(user)
    response = client.get("/settings/")
    assert response.status_code == 200
    assert b"Profile" in response.content
    assert b"Active target preview" in response.content or b"Add target version" in response.content


def test_position_and_impact_chart_payloads(profile, target):
    from records.charts import opportunity_impact, position_vs_target
    from records.compass import evaluate_compass

    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("75.20"),
        body_fat_percent=Decimal("20.30"),
        muscle_percent=Decimal("35.40"),
    )
    rows = position_vs_target(
        profile,
        ranges={
            "weight_min": target.weight_min_kg,
            "weight_max": target.weight_max_kg,
            "fat_min": target.body_fat_min_percent,
            "fat_max": target.body_fat_max_percent,
            "muscle_min": target.muscle_min_percent,
            "muscle_max": target.muscle_max_percent,
        },
    )
    assert len(rows) == 3
    assert rows[0]["marker_pct"] is not None
    snap = evaluate_compass(profile)
    impact = opportunity_impact(
        [o for o in snap.opportunities],
        current_alignment=float(snap.alignment) if snap.alignment is not None else None,
    )
    assert "available" in impact
    if impact["available"] and impact["bars"] and snap.alignment is not None:
        top = impact["bars"][0]
        assert top["start_pct"] == pytest.approx(float(snap.alignment), abs=0.05)
        assert top["width_pct"] == pytest.approx(top["alignment_gain"], abs=0.2)
        assert top["start_pct"] + top["width_pct"] <= 100.5


def test_compass_page_includes_decision_charts(client, user, profile, target):
    client.force_login(user)
    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("75.20"),
        body_fat_percent=Decimal("20.30"),
        muscle_percent=Decimal("35.40"),
    )
    response = client.get("/compass/")
    assert response.status_code == 200
    assert b"Position versus destination" in response.content
    assert b"range-track" in response.content
    assert b"Opportunity impact" in response.content


def test_preferences_change_scoring(profile, target):
    from records.models import CompassPreferences
    from records.preferences import resolve_algorithm
    from records.scoring import component_scores, overall_alignment

    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("75.20"),
        body_fat_percent=Decimal("20.30"),
        muscle_percent=Decimal("35.40"),
    )
    default_algo = resolve_algorithm(profile)
    comps = component_scores(
        weight_kg=Decimal("75.20"),
        body_fat_percent=Decimal("20.30"),
        muscle_percent=Decimal("35.40"),
        weight_min=target.weight_min_kg,
        weight_max=target.weight_max_kg,
        fat_min=target.body_fat_min_percent,
        fat_max=target.body_fat_max_percent,
        muscle_min=target.muscle_min_percent,
        muscle_max=target.muscle_max_percent,
        algorithm=default_algo,
    )
    default_score, _ = overall_alignment(comps, algorithm=default_algo)

    CompassPreferences.objects.create(
        profile=profile,
        fat_soft_pp=Decimal("1.00"),
        fat_hard_pp=Decimal("3.00"),
    )
    tight = resolve_algorithm(profile)
    comps2 = component_scores(
        weight_kg=Decimal("75.20"),
        body_fat_percent=Decimal("20.30"),
        muscle_percent=Decimal("35.40"),
        weight_min=target.weight_min_kg,
        weight_max=target.weight_max_kg,
        fat_min=target.body_fat_min_percent,
        fat_max=target.body_fat_max_percent,
        muscle_min=target.muscle_min_percent,
        muscle_max=target.muscle_max_percent,
        algorithm=tight,
    )
    tight_score, _ = overall_alignment(comps2, algorithm=tight)
    assert tight_score < default_score
