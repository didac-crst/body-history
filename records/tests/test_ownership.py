from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from records.models import Measurement, Profile, ProfileTarget, TrustedDevice
from records.trusted_devices import hash_token


pytestmark = pytest.mark.django_db


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username="other", password="pass")


@pytest.fixture
def other_profile(other_user):
    return Profile.objects.create(
        user=other_user,
        display_name="Other",
        height_cm=Decimal("170.00"),
        timezone="Europe/Paris",
    )


@pytest.fixture
def other_measurement(other_profile):
    return Measurement.objects.create(
        profile=other_profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("99.00"),
        body_fat_percent=Decimal("25.00"),
        muscle_percent=Decimal("30.00"),
    )


def test_one_profile_per_user(user, profile):
    from django.db import IntegrityError

    assert user.body_profile.id == profile.id
    with pytest.raises(IntegrityError):
        Profile.objects.create(
            user=user,
            display_name="Second",
            height_cm=Decimal("170.00"),
            timezone="Europe/Paris",
        )


def test_settings_shows_own_profile_only(client, user, profile, other_profile):
    client.force_login(user)
    response = client.get("/settings/")
    assert response.status_code == 200
    assert profile.display_name.encode() in response.content
    assert other_profile.display_name.encode() not in response.content
    assert b"Add profile" not in response.content
    assert b"switch-profile" not in response.content


def test_measurement_urls_reject_foreign_ids(client, user, profile, other_measurement):
    client.force_login(user)
    pk = other_measurement.pk
    assert client.get(f"/measurements/{pk}/edit/").status_code == 404
    assert client.post(f"/measurements/{pk}/delete/").status_code == 404


def test_foreign_targets_not_shown(client, user, profile, other_profile):
    ProfileTarget.objects.create(
        profile=other_profile,
        valid_from=date(2020, 1, 1),
        weight_min_kg=Decimal("50.00"),
        weight_max_kg=Decimal("51.00"),
    )
    client.force_login(user)
    response = client.get("/settings/")
    assert b"50.00" not in response.content
    assert b"51.00" not in response.content


def test_export_excludes_foreign_measurements(client, user, profile, other_measurement):
    Measurement.objects.create(
        profile=profile,
        measured_at=timezone.now(),
        weight_kg=Decimal("80.00"),
        body_fat_percent=Decimal("20.00"),
        muscle_percent=Decimal("40.00"),
    )
    client.force_login(user)
    body = client.get("/history/export.csv").content.decode()
    assert "80.00" in body
    assert "99.00" not in body


def test_compass_uses_only_own_profile(client, user, profile, other_measurement):
    client.force_login(user)
    response = client.get("/compass/")
    assert response.status_code == 200
    assert b"99" not in response.content


def test_trusted_devices_scoped_to_user(user, other_user):
    TrustedDevice.objects.create(
        user=other_user,
        token_hash=hash_token("other-token"),
        label="other",
        expires_at=timezone.now() + timedelta(days=30),
    )
    assert TrustedDevice.objects.filter(user=user).count() == 0
    assert TrustedDevice.objects.filter(user=other_user).count() == 1
