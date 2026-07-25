from django.conf import settings

from .profiles import get_active_profile


def app_branding(request):
    ctx = {
        "app_name": "Body History",
        "app_subtitle": "Weight and body composition history",
        "imports_dir": str(settings.BODY_HISTORY_IMPORTS_DIR),
    }
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        ctx["active_profile"] = get_active_profile(request)
    return ctx
