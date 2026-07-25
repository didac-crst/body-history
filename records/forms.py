from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from .metrics import convert_fraction_to_percent, same_local_date_exists
from .models import CompassPreferences, Measurement, Profile, ProfileTarget


class LoginForm(AuthenticationForm):
    trust_device = forms.BooleanField(
        required=False,
        initial=True,
        label="Trust this device for 180 days",
    )


class MeasurementForm(forms.ModelForm):
    class Meta:
        model = Measurement
        fields = [
            "measured_at",
            "weight_kg",
            "body_fat_percent",
            "muscle_percent",
            "source",
            "notes",
            "conditions",
            "is_excluded",
            "exclusion_reason",
        ]
        widgets = {
            "measured_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "conditions": forms.Textarea(attrs={"rows": 2}),
            "exclusion_reason": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, profile=None, **kwargs):
        self.profile = profile
        super().__init__(*args, **kwargs)
        self.fields["measured_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        if not self.is_bound and not self.instance.pk:
            local_now = timezone.localtime()
            self.initial["measured_at"] = local_now.strftime("%Y-%m-%dT%H:%M")
            self.initial["source"] = Measurement.SOURCE_MANUAL
        self.warnings: list[str] = []

    def clean_body_fat_percent(self):
        value = self.cleaned_data.get("body_fat_percent")
        if value is not None and 0 < value <= 1:
            self.warnings.append(
                f"Body fat {value} looks like a fraction; converted to {convert_fraction_to_percent(value)}%."
            )
            return convert_fraction_to_percent(value)
        return value

    def clean_muscle_percent(self):
        value = self.cleaned_data.get("muscle_percent")
        if value is not None and 0 < value <= 1:
            self.warnings.append(
                f"Muscle {value} looks like a fraction; converted to {convert_fraction_to_percent(value)}%."
            )
            return convert_fraction_to_percent(value)
        return value

    def clean(self):
        cleaned = super().clean()
        measured_at = cleaned.get("measured_at")
        if measured_at and measured_at > timezone.now():
            self.warnings.append("Measurement date is in the future.")
        if self.profile and measured_at:
            if same_local_date_exists(
                self.profile, measured_at, exclude_id=self.instance.pk
            ):
                self.warnings.append(
                    "Another measurement already exists on this local date."
                )
        if cleaned.get("is_excluded") and not cleaned.get("exclusion_reason"):
            self.add_error("exclusion_reason", "Provide a reason when excluding.")
        return cleaned


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "display_name",
            "height_cm",
            "timezone",
            "date_format",
            "weight_unit",
            "smoothing_window_days",
            "include_excluded_in_summaries",
        ]
        widgets = {
            "display_name": forms.TextInput(),
            "timezone": forms.TextInput(),
            "date_format": forms.TextInput(),
            "weight_unit": forms.TextInput(),
        }


class ProfileTargetForm(forms.ModelForm):
    class Meta:
        model = ProfileTarget
        fields = [
            "valid_from",
            "valid_to",
            "weight_min_kg",
            "weight_max_kg",
            "body_fat_min_percent",
            "body_fat_max_percent",
            "muscle_min_percent",
            "muscle_max_percent",
        ]
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        pairs = [
            ("weight_min_kg", "weight_max_kg", "Weight"),
            ("body_fat_min_percent", "body_fat_max_percent", "Body fat"),
            ("muscle_min_percent", "muscle_max_percent", "Muscle"),
        ]
        configured = False
        for lo_name, hi_name, label in pairs:
            lo = cleaned.get(lo_name)
            hi = cleaned.get(hi_name)
            if lo is not None or hi is not None:
                configured = True
            if lo is not None and hi is not None and lo > hi:
                self.add_error(hi_name, f"{label} min must be <= max.")
        if not configured:
            self.add_error(None, "Configure at least one target dimension.")
        return cleaned


class CompassPreferencesForm(forms.ModelForm):
    class Meta:
        model = CompassPreferences
        fields = [
            "weight_importance",
            "body_fat_importance",
            "muscle_importance",
            "weight_soft_kg",
            "weight_hard_kg",
            "fat_soft_pp",
            "fat_hard_pp",
            "muscle_soft_pp",
            "muscle_hard_pp",
            "trend_window_days",
            "comparison_window_days",
        ]
        labels = {
            "weight_importance": "Weight importance (0–1)",
            "body_fat_importance": "Body fat importance (0–1)",
            "muscle_importance": "Muscle importance (0–1)",
            "weight_soft_kg": "Weight soft band (kg)",
            "weight_hard_kg": "Weight hard band (kg)",
            "fat_soft_pp": "Body fat soft band (pp)",
            "fat_hard_pp": "Body fat hard band (pp)",
            "muscle_soft_pp": "Muscle soft band (pp)",
            "muscle_hard_pp": "Muscle hard band (pp)",
            "trend_window_days": "Trend window (days)",
            "comparison_window_days": "Comparison window (days)",
        }

    def clean(self):
        cleaned = super().clean()
        total = (
            (cleaned.get("weight_importance") or 0)
            + (cleaned.get("body_fat_importance") or 0)
            + (cleaned.get("muscle_importance") or 0)
        )
        if total <= 0:
            self.add_error(None, "Importance weights must sum to a positive value.")
        return cleaned


class ImportPathForm(forms.Form):
    filename = forms.CharField(
        required=False,
        initial="Pes.xlsx",
        help_text="File name under the imports directory.",
    )
