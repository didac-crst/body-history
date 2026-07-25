from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from records.models import TrustedDevice
from records.trusted_devices import hash_token


pytestmark = pytest.mark.django_db


def test_logout_clears_trusted_device_and_stays_logged_out(client, user):
    client.force_login(user)
    device = TrustedDevice.objects.create(
        user=user,
        token_hash=hash_token("logout-token"),
        label="browser",
        expires_at=timezone.now() + timedelta(days=30),
    )
    client.cookies[settings.TRUSTED_DEVICE_COOKIE_NAME] = "logout-token"

    response = client.post("/logout/")
    assert response.status_code == 302
    assert "/login" in response.url

    device.refresh_from_db()
    assert device.revoked_at is not None
    assert response.cookies[settings.TRUSTED_DEVICE_COOKIE_NAME].value == ""

    follow = client.get("/")
    assert follow.status_code == 302
    assert "/login" in follow.url
