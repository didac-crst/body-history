from django.utils.deprecation import MiddlewareMixin

from .trusted_devices import login_from_trusted_device


class TrustedDeviceMiddleware(MiddlewareMixin):
    def process_request(self, request):
        login_from_trusted_device(request)
        return None
