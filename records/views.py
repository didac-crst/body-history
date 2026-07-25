from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ImportPathForm, LoginForm, MeasurementForm, ProfileForm, ProfileTargetForm
from .importer import import_workbook, parse_workbook, report_to_dict
from .metrics import (
    calculate_bmi,
    calculate_fat_mass_kg,
    convert_fraction_to_percent,
    dashboard_metrics,
    enrich_measurement,
    measurement_queryset,
    same_local_date_exists,
    smooth_series,
    target_for_date,
)
from .models import ImportBatch, Measurement, Profile, ProfileTarget, TrustedDevice
from .trusted_devices import (
    clear_trusted_device_cookie,
    issue_trusted_device,
    revoke_all_devices,
    revoke_device,
    set_trusted_device_cookie,
)


def get_or_create_default_profile() -> Profile:
    profile = Profile.objects.order_by("created_at").first()
    if profile:
        return profile
    return Profile.objects.create(
        display_name="Default",
        height_cm="181.00",
        timezone=settings.TIME_ZONE,
    )


class BodyHistoryLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, response_form):
        response = super().form_valid(response_form)
        if response_form.cleaned_data.get("trust_device"):
            _, raw = issue_trusted_device(self.request.user, self.request)
            set_trusted_device_cookie(response, raw)
            messages.success(self.request, "This device is now trusted for 180 days.")
        return response


@require_POST
@login_required
def logout_view(request):
    revoke_current = request.POST.get("revoke_device") == "1"
    logout_all = request.POST.get("logout_all") == "1"
    response = redirect("login")
    if logout_all:
        revoke_all_devices(request.user)
        clear_trusted_device_cookie(response)
        messages.info(request, "Signed out of all trusted devices.")
    elif revoke_current:
        raw = request.COOKIES.get(settings.TRUSTED_DEVICE_COOKIE_NAME)
        if raw:
            from .trusted_devices import hash_token

            device = TrustedDevice.objects.filter(
                user=request.user, token_hash=hash_token(raw), revoked_at__isnull=True
            ).first()
            if device:
                revoke_device(device)
        clear_trusted_device_cookie(response)
    logout(request)
    return response


def _parse_optional_percent(raw: str) -> Decimal | None:
    value = (raw or "").strip()
    if not value:
        return None
    number = Decimal(value)
    if 0 < number <= 1:
        return convert_fraction_to_percent(number)
    return number.quantize(Decimal("0.01"))


@login_required
@require_http_methods(["GET", "POST"])
def quick_add(request):
    """iPhone homescreen flow: weight → fat → muscle → date → review/save."""
    profile = get_or_create_default_profile()
    today = timezone.localdate()
    context = {
        "profile": profile,
        "today": today.isoformat(),
        "saved": False,
        "error": None,
        "warnings": [],
        "posted": {
            "weight_kg": "",
            "body_fat_percent": "",
            "muscle_percent": "",
            "measured_on": today.isoformat(),
        },
    }

    if request.method == "POST":
        warnings: list[str] = []
        posted = {
            "weight_kg": (request.POST.get("weight_kg") or "").strip(),
            "body_fat_percent": (request.POST.get("body_fat_percent") or "").strip(),
            "muscle_percent": (request.POST.get("muscle_percent") or "").strip(),
            "measured_on": (request.POST.get("measured_on") or today.isoformat()).strip(),
        }
        context["posted"] = posted
        try:
            weight_kg = Decimal(posted["weight_kg"])
            if weight_kg <= 0:
                raise ValueError("Weight must be greater than zero.")
            body_fat = _parse_optional_percent(posted["body_fat_percent"])
            muscle = _parse_optional_percent(posted["muscle_percent"])
            measured_day = date.fromisoformat(posted["measured_on"])
            measured_at = timezone.make_aware(
                datetime.combine(measured_day, datetime.min.time().replace(hour=8)),
                ZoneInfo(profile.timezone),
            )
            if body_fat is not None and (body_fat < 0 or body_fat > 100):
                raise ValueError("Body fat must be between 0 and 100.")
            if muscle is not None and (muscle < 0 or muscle > 100):
                raise ValueError("Muscle must be between 0 and 100.")
            if measured_at > timezone.now() + timedelta(days=1):
                warnings.append("Date is in the future.")
            if same_local_date_exists(profile, measured_at):
                warnings.append("Another measurement already exists on this date.")

            Measurement.objects.create(
                profile=profile,
                measured_at=measured_at,
                weight_kg=weight_kg.quantize(Decimal("0.01")),
                body_fat_percent=body_fat,
                muscle_percent=muscle,
                source=Measurement.SOURCE_MANUAL,
                notes="",
            )
            context["saved"] = True
            context["warnings"] = warnings
            context["saved_summary"] = {
                "weight_kg": str(weight_kg.quantize(Decimal("0.01"))),
                "body_fat_percent": str(body_fat) if body_fat is not None else "",
                "muscle_percent": str(muscle) if muscle is not None else "",
                "measured_on": measured_day.isoformat(),
            }
        except (InvalidOperation, ValueError, TypeError) as exc:
            context["error"] = str(exc)

    return render(request, "records/quick_add.html", context)


@login_required
def dashboard(request):
    profile = get_or_create_default_profile()
    metrics = dashboard_metrics(profile)
    return render(
        request,
        "records/dashboard.html",
        {"profile": profile, "metrics": metrics},
    )


@login_required
@require_http_methods(["GET", "POST"])
def measurement_create(request):
    profile = get_or_create_default_profile()
    form = MeasurementForm(request.POST or None, profile=profile)
    if request.method == "POST" and form.is_valid():
        measurement = form.save(commit=False)
        measurement.profile = profile
        measurement.save()
        for warning in form.warnings:
            messages.warning(request, warning)
        messages.success(request, "Measurement saved.")
        if request.POST.get("add_another") == "1":
            return redirect("measurement_create")
        return redirect("history")
    return render(
        request,
        "records/measurement_form.html",
        {"form": form, "title": "Add measurement", "profile": profile},
    )


@login_required
@require_http_methods(["GET", "POST"])
def measurement_edit(request, pk):
    profile = get_or_create_default_profile()
    measurement = get_object_or_404(Measurement, pk=pk, profile=profile)
    form = MeasurementForm(request.POST or None, instance=measurement, profile=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        for warning in form.warnings:
            messages.warning(request, warning)
        messages.success(request, "Measurement updated.")
        return redirect("history")
    return render(
        request,
        "records/measurement_form.html",
        {
            "form": form,
            "title": "Edit measurement",
            "profile": profile,
            "measurement": measurement,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def measurement_delete(request, pk):
    profile = get_or_create_default_profile()
    measurement = get_object_or_404(Measurement, pk=pk, profile=profile)
    if request.method == "POST":
        measurement.delete()
        messages.success(request, "Measurement deleted.")
        return redirect("history")
    return render(
        request,
        "records/measurement_confirm_delete.html",
        {"measurement": measurement},
    )


@login_required
def history(request):
    profile = get_or_create_default_profile()
    qs = profile.measurements.all()
    source = request.GET.get("source")
    if source:
        qs = qs.filter(source=source)
    excluded = request.GET.get("excluded")
    if excluded == "1":
        qs = qs.filter(is_excluded=True)
    elif excluded == "0":
        qs = qs.filter(is_excluded=False)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(notes__icontains=q) | Q(conditions__icontains=q))

    sort = request.GET.get("sort", "-measured_at")
    allowed = {
        "measured_at",
        "-measured_at",
        "weight_kg",
        "-weight_kg",
        "body_fat_percent",
        "-body_fat_percent",
        "muscle_percent",
        "-muscle_percent",
    }
    if sort not in allowed:
        sort = "-measured_at"
    qs = qs.order_by(sort)

    rows = [enrich_measurement(m, profile.height_cm) for m in qs[:500]]
    return render(
        request,
        "records/history.html",
        {
            "profile": profile,
            "rows": rows,
            "filters": {"source": source or "", "excluded": excluded or "", "q": q, "sort": sort},
        },
    )


@login_required
def export_csv(request):
    profile = get_or_create_default_profile()
    include_excluded = request.GET.get("excluded") == "1"
    qs = measurement_queryset(profile, include_excluded=include_excluded).order_by("measured_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="body-history-export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "measured_at",
            "weight_kg",
            "bmi",
            "body_fat_percent",
            "fat_mass_kg",
            "muscle_percent",
            "source",
            "notes",
            "conditions",
            "is_excluded",
            "exclusion_reason",
        ]
    )
    for measurement in qs:
        enriched = enrich_measurement(measurement, profile.height_cm)
        writer.writerow(
            [
                timezone.localtime(measurement.measured_at).isoformat(),
                measurement.weight_kg,
                enriched["bmi"],
                measurement.body_fat_percent or "",
                enriched["fat_mass_kg"] or "",
                measurement.muscle_percent or "",
                measurement.source,
                measurement.notes,
                measurement.conditions,
                measurement.is_excluded,
                measurement.exclusion_reason,
            ]
        )
    return response


@login_required
def chart_page(request):
    profile = get_or_create_default_profile()
    return render(request, "records/chart.html", {"profile": profile})


@login_required
def chart_data(request):
    profile = get_or_create_default_profile()
    metric = request.GET.get("metric", "weight_kg")
    range_key = request.GET.get("range", "1y")
    ranges = {
        "30d": 30,
        "90d": 90,
        "1y": 365,
        "5y": 365 * 5,
        "all": None,
    }
    days = ranges.get(range_key, 365)
    qs = measurement_queryset(profile).order_by("measured_at")
    if days is not None:
        start = timezone.now() - timedelta(days=days)
        qs = qs.filter(measured_at__gte=start)

    points = []
    for measurement in qs:
        if metric == "bmi":
            value = calculate_bmi(measurement.weight_kg, profile.height_cm)
        elif metric == "fat_mass_kg":
            value = calculate_fat_mass_kg(measurement.weight_kg, measurement.body_fat_percent)
        elif metric == "body_fat_percent":
            value = measurement.body_fat_percent
        elif metric == "muscle_percent":
            value = measurement.muscle_percent
        else:
            value = measurement.weight_kg
        if value is None:
            continue
        points.append((measurement.measured_at, float(value)))

    smoothed = smooth_series(points, profile.smoothing_window_days)
    latest_date = timezone.localdate()
    target = target_for_date(profile, latest_date)
    target_value = None
    if target:
        mapping = {
            "weight_kg": target.target_weight_kg,
            "bmi": target.target_bmi,
            "body_fat_percent": target.target_body_fat_percent,
            "muscle_percent": target.target_muscle_percent,
            "fat_mass_kg": None,
        }
        target_value = mapping.get(metric)
        target_value = float(target_value) if target_value is not None else None

    return JsonResponse(
        {
            "metric": metric,
            "range": range_key,
            "raw": [
                {"t": timezone.localtime(ts).isoformat(), "v": value} for ts, value in points
            ],
            "trend": [
                {"t": timezone.localtime(ts).isoformat(), "v": value}
                for ts, value in smoothed
            ],
            "target": target_value,
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    profile = get_or_create_default_profile()
    form = ProfileForm(request.POST or None, instance=profile)
    target_form = ProfileTargetForm(prefix="target")
    if request.method == "POST" and "save_profile" in request.POST:
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            return redirect("settings")
    if request.method == "POST" and "save_target" in request.POST:
        target_form = ProfileTargetForm(request.POST, prefix="target")
        if target_form.is_valid():
            target = target_form.save(commit=False)
            target.profile = profile
            target.save()
            messages.success(request, "Target version saved.")
            return redirect("settings")

    devices = TrustedDevice.objects.filter(user=request.user).order_by("-last_seen_at")
    targets = profile.targets.all()
    return render(
        request,
        "records/settings.html",
        {
            "profile": profile,
            "form": form,
            "target_form": target_form,
            "targets": targets,
            "devices": devices,
        },
    )


@login_required
@require_POST
def revoke_trusted_device(request, pk):
    device = get_object_or_404(TrustedDevice, pk=pk, user=request.user)
    revoke_device(device)
    messages.success(request, "Trusted device revoked.")
    return redirect("settings")


@login_required
@require_POST
def logout_all_devices(request):
    revoke_all_devices(request.user)
    update_session_auth_hash(request, request.user)
    response = redirect("settings")
    clear_trusted_device_cookie(response)
    messages.success(request, "All trusted devices revoked.")
    return response


@login_required
@require_http_methods(["GET", "POST"])
def import_page(request):
    profile = get_or_create_default_profile()
    form = ImportPathForm(request.POST or None)
    report = None
    batch = None
    imports_dir = Path(settings.BODY_HISTORY_IMPORTS_DIR)
    available = sorted(p.name for p in imports_dir.glob("*.xlsx")) if imports_dir.exists() else []

    if request.method == "POST" and form.is_valid():
        filename = form.cleaned_data.get("filename") or "Pes.xlsx"
        path = (imports_dir / filename).resolve()
        if not str(path).startswith(str(imports_dir.resolve())) or not path.exists():
            raise Http404("Import file not found")
        action = request.POST.get("action")
        if action == "dry_run":
            report = report_to_dict(parse_workbook(path))
            request.session["last_dry_run_hash"] = report["file_hash"]
            request.session["last_dry_run_file"] = filename
        elif action == "import":
            parsed = parse_workbook(path)
            batch = import_workbook(profile, path, report=parsed)
            if not profile.targets.exists():
                ProfileTarget.objects.create(
                    profile=profile,
                    valid_from=date(2005, 1, 1),
                    target_bmi="22.00",
                    target_body_fat_percent="17.00",
                    target_muscle_percent="39.80",
                )
            messages.success(
                request,
                f"Import finished: {batch.accepted_count} accepted, {batch.rejected_count} rejected.",
            )
            report = report_to_dict(parsed)
            report["import_batch_id"] = str(batch.id)

    batches = ImportBatch.objects.filter(profile=profile)[:20]
    return render(
        request,
        "records/import.html",
        {
            "form": form,
            "report": report,
            "batch": batch,
            "batches": batches,
            "available": available,
            "profile": profile,
        },
    )
