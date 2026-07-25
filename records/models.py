import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.TextField()
    height_cm = models.DecimalField(max_digits=5, decimal_places=2)
    timezone = models.TextField(default="Europe/Paris")
    weight_unit = models.TextField(default="kg")
    date_format = models.TextField(default="%Y-%m-%d")
    smoothing_window_days = models.PositiveIntegerField(default=14)
    include_excluded_in_summaries = models.BooleanField(default=False)

    class Meta:
        db_table = "profiles"

    def __str__(self) -> str:
        return self.display_name


class ProfileTarget(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="targets")
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    # Preferred range fields for Body Compass.
    weight_min_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_max_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    body_fat_min_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    body_fat_max_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    muscle_min_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    muscle_max_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # Legacy single-value fields kept for migration compatibility.
    target_weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    target_bmi = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    target_body_fat_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    target_muscle_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    class Meta:
        db_table = "profile_targets"
        ordering = ["-valid_from", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=models.F("valid_from")),
                name="profile_targets_valid_range",
            ),
            models.CheckConstraint(
                condition=Q(weight_min_kg__isnull=True)
                | Q(weight_max_kg__isnull=True)
                | Q(weight_min_kg__lte=models.F("weight_max_kg")),
                name="profile_targets_weight_min_lte_max",
            ),
            models.CheckConstraint(
                condition=Q(body_fat_min_percent__isnull=True)
                | Q(body_fat_max_percent__isnull=True)
                | Q(body_fat_min_percent__lte=models.F("body_fat_max_percent")),
                name="profile_targets_fat_min_lte_max",
            ),
            models.CheckConstraint(
                condition=Q(muscle_min_percent__isnull=True)
                | Q(muscle_max_percent__isnull=True)
                | Q(muscle_min_percent__lte=models.F("muscle_max_percent")),
                name="profile_targets_muscle_min_lte_max",
            ),
        ]

    def clean(self):
        super().clean()
        pairs = [
            ("weight_min_kg", "weight_max_kg", "Weight"),
            ("body_fat_min_percent", "body_fat_max_percent", "Body fat"),
            ("muscle_min_percent", "muscle_max_percent", "Muscle"),
        ]
        configured = False
        for lo_name, hi_name, label in pairs:
            lo = getattr(self, lo_name)
            hi = getattr(self, hi_name)
            if lo is not None or hi is not None:
                configured = True
            if lo is not None and hi is not None and lo > hi:
                raise ValidationError({hi_name: f"{label} min must be <= max."})
        legacy = any(
            [
                self.target_weight_kg,
                self.target_body_fat_percent,
                self.target_muscle_percent,
                self.target_bmi,
            ]
        )
        if not configured and not legacy:
            raise ValidationError("Configure at least one target dimension.")

    def __str__(self) -> str:
        return f"{self.profile} from {self.valid_from}"


class Measurement(TimeStampedModel):
    SOURCE_MANUAL = "manual"
    SOURCE_IMPORT = "import"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_IMPORT, "Import"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="measurements"
    )
    measured_at = models.DateTimeField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    body_fat_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    muscle_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    source = models.TextField(choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    notes = models.TextField(blank=True, default="")
    conditions = models.TextField(blank=True, default="")
    is_excluded = models.BooleanField(default=False)
    exclusion_reason = models.TextField(blank=True, default="")
    legacy_payload = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "measurements"
        ordering = ["-measured_at", "-created_at"]
        indexes = [
            models.Index(fields=["profile", "measured_at"]),
            models.Index(fields=["profile", "is_excluded", "measured_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(weight_kg__gt=0), name="measurements_weight_gt_0"),
            models.CheckConstraint(
                condition=Q(body_fat_percent__isnull=True)
                | (Q(body_fat_percent__gte=0) & Q(body_fat_percent__lte=100)),
                name="measurements_body_fat_range",
            ),
            models.CheckConstraint(
                condition=Q(muscle_percent__isnull=True)
                | (Q(muscle_percent__gte=0) & Q(muscle_percent__lte=100)),
                name="measurements_muscle_range",
            ),
        ]

    def clean(self):
        super().clean()
        if self.weight_kg is not None and self.weight_kg <= 0:
            raise ValidationError({"weight_kg": "Weight must be greater than zero."})
        for field in ("body_fat_percent", "muscle_percent"):
            value = getattr(self, field)
            if value is not None and (value < 0 or value > 100):
                raise ValidationError({field: "Must be between 0 and 100."})

    def __str__(self) -> str:
        return f"{self.measured_at.isoformat()} {self.weight_kg} kg"


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="import_batches"
    )
    filename = models.TextField()
    file_hash = models.TextField()
    imported_at = models.DateTimeField(default=timezone.now)
    row_count = models.IntegerField()
    accepted_count = models.IntegerField()
    rejected_count = models.IntegerField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "import_batches"
        ordering = ["-imported_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "file_hash"],
                name="import_batches_profile_file_hash_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.filename} @ {self.imported_at.isoformat()}"


class MeasurementImportRow(models.Model):
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name="rows"
    )
    source_sheet = models.TextField(blank=True, default="")
    source_row = models.IntegerField(null=True, blank=True)
    raw_payload = models.JSONField()
    measurement = models.ForeignKey(
        Measurement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_rows",
    )
    status = models.TextField(choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "measurement_import_rows"
        indexes = [
            models.Index(fields=["import_batch", "source_sheet", "source_row"]),
        ]


class TrustedDevice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trusted_devices"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    label = models.TextField(blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "trusted_devices"
        ordering = ["-last_seen_at"]

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at > timezone.now()

    def __str__(self) -> str:
        return self.label or f"Device {self.id}"


def decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
