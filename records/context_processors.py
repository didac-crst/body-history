from django.conf import settings

from .profiles import get_active_profile, list_profiles


def app_branding(request):
    ctx = {
        "app_name": "Body History",
        "app_subtitle": "Weight and body composition history",
        "imports_dir": str(settings.BODY_HISTORY_IMPORTS_DIR),
    }
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        active = get_active_profile(request)
        ctx["active_profile"] = active
        ctx["profiles"] = list(list_profiles())
    return ctx
