"""Shared middleware package."""

from shared.middleware.gateway_enforcer import GatewayEnforcementMiddleware

__all__ = ["GatewayEnforcementMiddleware"]
