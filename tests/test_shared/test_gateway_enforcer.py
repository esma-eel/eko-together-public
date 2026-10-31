"""Unit tests for GatewayEnforcementMiddleware."""

import json
from unittest.mock import MagicMock

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from shared.middleware.gateway_enforcer import GatewayEnforcementMiddleware


def dummy_view(request):
    return HttpResponse(b"ok", status=200)


def test_gateway_enforcer_blocks_direct_access_when_restricted(monkeypatch):
    """When direct access is disabled and no gateway header is sent, returns 403."""
    monkeypatch.setenv("ALLOW_DIRECT_SERVICE_ACCESS", "false")
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Temporarily hide 'pytest' from sys.modules inside the call check
    monkeypatch.setattr("sys.modules", {k: v for k, v in __import__("sys").modules.items() if k != "pytest"})

    middleware = GatewayEnforcementMiddleware(dummy_view)
    factory = RequestFactory()
    request = factory.get("/api/v1/auth/me/")

    response = middleware(request)
    assert response.status_code == 403
    data = json.loads(response.content)
    assert "Direct microservice access is deprecated" in data["error"]
    assert "http://localhost/api/v1/auth/me/" == data["gateway_url"]


def test_gateway_enforcer_allows_request_from_gateway(monkeypatch):
    """When request has X-Gateway-Origin: eko-gateway, request succeeds."""
    monkeypatch.setenv("ALLOW_DIRECT_SERVICE_ACCESS", "false")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr("sys.modules", {k: v for k, v in __import__("sys").modules.items() if k != "pytest"})

    middleware = GatewayEnforcementMiddleware(dummy_view)
    factory = RequestFactory()
    request = factory.get("/api/v1/auth/me/", HTTP_X_GATEWAY_ORIGIN="eko-gateway")

    response = middleware(request)
    assert response.status_code == 200
    assert response.content == b"ok"


def test_gateway_enforcer_allows_direct_when_flag_enabled(monkeypatch):
    """When ALLOW_DIRECT_SERVICE_ACCESS=true, direct access succeeds without gateway header."""
    monkeypatch.setenv("ALLOW_DIRECT_SERVICE_ACCESS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")

    middleware = GatewayEnforcementMiddleware(dummy_view)
    factory = RequestFactory()
    request = factory.get("/api/v1/auth/me/")

    response = middleware(request)
    assert response.status_code == 200
    assert response.content == b"ok"


def test_gateway_enforcer_with_custom_secret_success(monkeypatch):
    """When a custom GATEWAY_ORIGIN_SECRET is configured, matching header succeeds."""
    monkeypatch.setenv("ALLOW_DIRECT_SERVICE_ACCESS", "false")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GATEWAY_ORIGIN_SECRET", "super-secret-gateway-token-xyz")
    monkeypatch.setattr("sys.modules", {k: v for k, v in __import__("sys").modules.items() if k != "pytest"})

    middleware = GatewayEnforcementMiddleware(dummy_view)
    factory = RequestFactory()
    request = factory.get("/api/v1/auth/me/", HTTP_X_GATEWAY_ORIGIN="super-secret-gateway-token-xyz")

    response = middleware(request)
    assert response.status_code == 200
    assert response.content == b"ok"


def test_gateway_enforcer_with_custom_secret_rejects_old_or_invalid_secret(monkeypatch):
    """When a custom GATEWAY_ORIGIN_SECRET is set, requests with default or invalid token are blocked."""
    monkeypatch.setenv("ALLOW_DIRECT_SERVICE_ACCESS", "false")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GATEWAY_ORIGIN_SECRET", "super-secret-gateway-token-xyz")
    monkeypatch.setattr("sys.modules", {k: v for k, v in __import__("sys").modules.items() if k != "pytest"})

    middleware = GatewayEnforcementMiddleware(dummy_view)
    factory = RequestFactory()

    # Sending old default secret should be rejected
    request = factory.get("/api/v1/auth/me/", HTTP_X_GATEWAY_ORIGIN="eko-gateway")
    response = middleware(request)
    assert response.status_code == 403

    # Sending invalid secret should be rejected
    request_bad = factory.get("/api/v1/auth/me/", HTTP_X_GATEWAY_ORIGIN="wrong-token")
    response_bad = middleware(request_bad)
    assert response_bad.status_code == 403

