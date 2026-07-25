from decimal import Decimal

import pytest

from records.models import Profile


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="owner", password="pass")


@pytest.fixture
def profile(user):
    return Profile.objects.create(
        user=user,
        display_name="Test",
        height_cm=Decimal("181.00"),
        timezone="Europe/Paris",
    )
