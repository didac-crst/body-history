"""CSRF failure handling with a recoverable login path."""

from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse
from django.views.csrf import csrf_failure as django_csrf_failure


def csrf_failure(request, reason=""):
    # Never leave the user on Django's raw 403 after a stale login POST.
    # A bad token cannot be accepted; instead open a fresh login form.
    path = request.path.rstrip("/")
    if path.endswith("login") or request.path in {"/login/", "/login"}:
        return redirect(reverse("login") + "?expired=1")
    return django_csrf_failure(request, reason=reason)
