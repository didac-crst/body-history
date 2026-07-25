from django.contrib import admin

from .models import (
    CompassPreferences,
    ImportBatch,
    Measurement,
    MeasurementImportRow,
    Profile,
    ProfileTarget,
    TrustedDevice,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "height_cm", "timezone", "updated_at")
    list_filter = ("user",)
    search_fields = ("display_name", "user__username")


@admin.register(ProfileTarget)
class ProfileTargetAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "valid_from",
        "valid_to",
        "target_bmi",
        "target_body_fat_percent",
        "target_muscle_percent",
    )


@admin.register(CompassPreferences)
class CompassPreferencesAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "weight_importance",
        "body_fat_importance",
        "muscle_importance",
        "fat_soft_pp",
        "fat_hard_pp",
        "updated_at",
    )


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = (
        "measured_at",
        "weight_kg",
        "body_fat_percent",
        "muscle_percent",
        "source",
        "is_excluded",
    )
    list_filter = ("source", "is_excluded")
    # Avoid logging/displaying huge dumps of measurement values in admin actions.


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "filename",
        "imported_at",
        "row_count",
        "accepted_count",
        "rejected_count",
        "file_hash",
    )
    readonly_fields = ("file_hash", "metadata")


@admin.register(MeasurementImportRow)
class MeasurementImportRowAdmin(admin.ModelAdmin):
    list_display = ("import_batch", "source_sheet", "source_row", "status")
    list_filter = ("status",)


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "created_at", "last_seen_at", "expires_at", "revoked_at")
    readonly_fields = ("token_hash",)
