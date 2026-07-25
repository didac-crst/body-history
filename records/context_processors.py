from django.conf import settings


def app_branding(request):
    return {
        "app_name": "Body History",
        "app_subtitle": "Weight and body composition history",
        "imports_dir": str(settings.BODY_HISTORY_IMPORTS_DIR),
    }
