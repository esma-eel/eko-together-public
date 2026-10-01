"""Middleware to enforce API Gateway routing and prevent direct port access."""

from __future__ import annotations

import os
import secrets
import sys
from typing import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse


class GatewayEnforcementMiddleware:
    """Enforces that all external HTTP requests are routed through the API Gateway (Port 80).

    Direct access to individual microservice ports (e.g. localhost:8001..8007) is deprecated
    and blocked by default with HTTP 403 Forbidden.

    This restriction can be disabled / bypassed in the following scenarios:
    1. ALLOW_DIRECT_SERVICE_ACCESS=true in .env / environment variables.
    2. ENVIRONMENT=testing or running via pytest / unit tests.
    3. The request originated from the API Gateway with a valid secret token
       (HTTP_X_GATEWAY_ORIGIN matching GATEWAY_ORIGIN_SECRET, default 'eko-gateway').
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Check if direct access is enabled globally via env or during testing
        allow_direct = (
            os.getenv("ALLOW_DIRECT_SERVICE_ACCESS", "False").lower() in ("true", "1", "yes")
            or os.getenv("ENVIRONMENT") == "testing"
            or "pytest" in sys.modules
        )

        if not allow_direct:
            gateway_origin = request.META.get("HTTP_X_GATEWAY_ORIGIN", "")
            expected_secret = os.getenv("GATEWAY_ORIGIN_SECRET", "eko-gateway")

            # Constant-time comparison to prevent timing attacks
            if not gateway_origin or not secrets.compare_digest(gateway_origin, expected_secret):
                return JsonResponse(
                    {
                        "error": "Direct microservice access is deprecated and disabled.",
                        "detail": (
                            "All API requests must be routed through the central API Gateway at "
                            f"http://localhost (Port 80). Attempted direct path: {request.path}"
                        ),
                        "gateway_url": f"http://localhost{request.path}",
                        "swagger_portal": "http://localhost/docs/",
                        "bypass_instruction": (
                            "To enable direct port access for isolated debugging, set "
                            "ALLOW_DIRECT_SERVICE_ACCESS=true in your .env file and restart services."
                        ),
                    },
                    status=403,
                )

        return self.get_response(request)
