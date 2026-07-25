from django.test import Client, override_settings
import pytest


pytestmark = pytest.mark.django_db


@override_settings(ROOT_URLCONF="config.urls")
def test_login_csrf_failure_refreshes_form_instead_of_403():
    client = Client(enforce_csrf_checks=True)
    # Establish a real session/token first.
    client.get("/login/")
    # Submit an obviously wrong token.
    response = client.post(
        "/login/",
        {
            "username": "x",
            "password": "y",
            "csrfmiddlewaretoken": "not-a-valid-token",
        },
    )
    assert response.status_code == 302
    assert "/login/" in response.url
    assert "expired=1" in response.url
    follow = client.get(response.url)
    assert follow.status_code == 200
    assert b"out of date" in follow.content
