"""Authentication DMR Controllers for User & Auth Service.

Implements signup, login with throttling, token refresh, token logout/blacklist,
stateless password reset flow, and password change.
"""

from __future__ import annotations

from http import HTTPStatus

from django.conf import settings
from django.utils import timezone
from dmr import Body, Controller, Query, modify
from dmr.plugins.msgspec import MsgspecSerializer
from dmr.throttling import Rate, SyncThrottle
from dmr.throttling.algorithms import LeakyBucket
from dmr.throttling.cache_keys import RemoteAddr

from services.auth_user_service.apps.accounts.models import (
    User,
    UserProfile,
)
from services.auth_user_service.apps.accounts.schemas import (
    CurrentUserResponseDTO,
    LoginRequestDTO,
    LoginResponseDTO,
    LogoutRequestDTO,
    MessageResponseDTO,
    PasswordChangeDTO,
    PasswordResetConfirmDTO,
    PasswordResetRequestDTO,
    PasswordVerifyTokenQueryDTO,
    PasswordVerifyTokenResponseDTO,
    ProfileSummaryDTO,
    SignupRequestDTO,
    SignupResponseDTO,
    TokenPairDTO,
    TokenRefreshRequestDTO,
    TokenRefreshResponseDTO,
    UserSummaryDTO,
)
from services.auth_user_service.apps.accounts.security import (
    AuthenticatedUserHttpRequest,
    RS256JWTSyncAuth,
)
from services.auth_user_service.apps.accounts.services import (
    create_user_tokens,
    decode_user_id,
    encode_user_id,
    is_token_revoked,
    log_user_action,
    password_reset_token_generator,
    revoke_token,
)
from shared.exceptions.base import (
    AuthenticationFailedException,
    ConflictException,
    PermissionDeniedException,
    ValidationException,
)
from shared.exceptions.handlers import domain_exception_to_dmr_error
from shared.jwt.tokens import (
    create_access_token,
    load_private_key,
    load_public_key,
    verify_and_decode_token,
)


class SignupController(Controller[MsgspecSerializer]):
    """Register a new user and generate RS256 token pair."""

    @modify(status_code=HTTPStatus.CREATED)
    def post(self, parsed_body: Body[SignupRequestDTO]) -> SignupResponseDTO:
        """Create new User and UserProfile, emit SIGNUP audit log, and return tokens."""
        # Validate unique constraints
        if User.objects.filter(username__iexact=parsed_body.username.strip()).exists():
            raise domain_exception_to_dmr_error(
                ConflictException("A user with this username already exists.")
            )

        if User.objects.filter(email__iexact=parsed_body.email.strip()).exists():
            raise domain_exception_to_dmr_error(
                ConflictException("A user with this email already exists.")
            )

        if len(parsed_body.password) < 8:
            raise domain_exception_to_dmr_error(
                ValidationException("Password must contain at least 8 characters.")
            )

        # Create user & profile atomically
        user = User.objects.create_user(
            username=parsed_body.username.strip(),
            email=parsed_body.email.strip().lower(),
            password=parsed_body.password,
        )
        profile = UserProfile.objects.create(
            user=user,
            display_name=parsed_body.display_name.strip() or user.username,
        )

        access, refresh = create_user_tokens(user)

        log_user_action(
            self.request,
            action="SIGNUP",
            user_profile=profile,
            target_type="USER",
            target_id=str(user.id),
        )

        return SignupResponseDTO(
            user=UserSummaryDTO(
                id=str(user.id),
                username=user.username,
                email=user.email,
            ),
            profile=ProfileSummaryDTO(
                id=str(profile.id),
                display_name=profile.display_name,
            ),
            tokens=TokenPairDTO(
                access=access,
                refresh=refresh,
            ),
        )


class LoginController(Controller[MsgspecSerializer]):
    """Authenticate user with username or email and return RS256 JWT tokens."""

    @modify(
        status_code=HTTPStatus.OK,
        throttling=[
            SyncThrottle(
                15,
                Rate.minute,
                algorithm=LeakyBucket(),
                cache_key=RemoteAddr(runs_before_auth=True),
            ),
        ],
    )
    def post(self, parsed_body: Body[LoginRequestDTO]) -> LoginResponseDTO:
        """Authenticate user credentials and issue RS256 JWT token pair."""
        ident = parsed_body.email_or_username.strip()
        user = (
            User.objects.filter(username__iexact=ident).select_related("profile").first()
            or User.objects.filter(email__iexact=ident).select_related("profile").first()
        )

        if not user or not user.check_password(parsed_body.password):
            log_user_action(
                self.request,
                action="LOGIN_FAILED",
                user_profile=None,
                target_type="AUTH",
                metadata={"identifier": ident},
            )
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Invalid username, email, or password.")
            )

        if not user.is_active:
            raise domain_exception_to_dmr_error(
                PermissionDeniedException("This account is currently deactivated.")
            )

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        access, refresh = create_user_tokens(user)

        log_user_action(
            self.request,
            action="LOGIN",
            user_profile=user.profile,
            target_type="USER",
            target_id=str(user.id),
        )

        return LoginResponseDTO(
            user=UserSummaryDTO(
                id=str(user.id),
                username=user.username,
                email=user.email,
            ),
            profile_id=str(user.profile.id),
            tokens=TokenPairDTO(
                access=access,
                refresh=refresh,
            ),
        )


class TokenRefreshController(Controller[MsgspecSerializer]):
    """Issue a new access token using a valid, unrevoked refresh token."""

    @modify(status_code=HTTPStatus.OK)
    def post(self, parsed_body: Body[TokenRefreshRequestDTO]) -> TokenRefreshResponseDTO:
        """Verify refresh token and issue new RS256 access token."""
        refresh_token = parsed_body.refresh.strip()
        if is_token_revoked(refresh_token):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Refresh token has been revoked.")
            )

        public_key_pem = load_public_key(settings.JWT_PUBLIC_KEY_PATH)
        try:
            claims = verify_and_decode_token(
                token=refresh_token,
                public_key_pem=public_key_pem,
                issuer=settings.JWT_ISSUER,
                audience=settings.JWT_AUDIENCE,
                expected_token_type="refresh",
            )
        except AuthenticationFailedException as exc:
            raise domain_exception_to_dmr_error(exc) from exc
        except Exception as exc:
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException(f"Invalid refresh token: {exc}")
            ) from exc

        user = (
            User.objects.filter(id=claims.user_id, is_active=True).select_related("profile").first()
        )
        if not user:
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Associated user not found or inactive.")
            )

        roles = ["user"]
        if user.is_superuser:
            roles.extend(["admin", "superuser"])
        elif user.is_staff:
            roles.append("staff")

        private_key_pem = load_private_key(settings.JWT_PRIVATE_KEY_PATH)
        new_access = create_access_token(
            user_id=user.id,
            profile_id=user.profile.id,
            username=user.username,
            roles=roles,
            private_key_pem=private_key_pem,
            expiration_minutes=settings.JWT_ACCESS_EXPIRATION_MINUTES,
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )

        return TokenRefreshResponseDTO(access=new_access)


class LogoutController(Controller[MsgspecSerializer]):
    """Blacklist the provided refresh token and invalidate authentication session."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    @modify(status_code=HTTPStatus.NO_CONTENT)
    def post(self, parsed_body: Body[LogoutRequestDTO]) -> None:
        """Revoke refresh token in blacklist and log LOGOUT action."""
        refresh_token = parsed_body.refresh.strip()
        revoke_token(
            refresh_token,
            user_id=self.request.user.id,
            token_type="refresh",
        )

        log_user_action(
            self.request,
            action="LOGOUT",
            user_profile=self.request.profile,
            target_type="AUTH",
            target_id=str(self.request.user.id),
        )


class PasswordResetRequestController(Controller[MsgspecSerializer]):
    """Initiate stateless password recovery via HMAC token."""

    @modify(status_code=HTTPStatus.OK)
    def post(self, parsed_body: Body[PasswordResetRequestDTO]) -> MessageResponseDTO:
        """Generate stateless HMAC reset token and dispatch email link (no enumeration)."""
        email = parsed_body.email.strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            token = password_reset_token_generator.make_token(user)
            uid = encode_user_id(user.id)
            log_user_action(
                self.request,
                action="PASSWORD_RESET_REQUEST",
                user_profile=user.profile,
                target_type="USER",
                target_id=str(user.id),
                metadata={"uid": uid, "token": token},
            )

        # Always return identical response to prevent email enumeration
        return MessageResponseDTO(
            message="If an account matches this email, a reset link has been dispatched."
        )


class PasswordVerifyTokenController(Controller[MsgspecSerializer]):
    """Verify validity of password reset token from disposable email link."""

    def get(
        self, parsed_query: Query[PasswordVerifyTokenQueryDTO]
    ) -> PasswordVerifyTokenResponseDTO:
        """Check whether uid and token correspond to a valid, unconsumed reset request."""
        user_id = decode_user_id(parsed_query.uid)
        user = User.objects.filter(id=user_id, is_active=True).first()

        if not user or not password_reset_token_generator.check_token(user, parsed_query.token):
            raise domain_exception_to_dmr_error(
                ValidationException("Reset token is invalid or has expired.")
            )

        return PasswordVerifyTokenResponseDTO(valid=True)


class PasswordResetConfirmController(Controller[MsgspecSerializer]):
    """Confirm password reset using disposable token and set new credentials."""

    @modify(status_code=HTTPStatus.OK)
    def post(self, parsed_body: Body[PasswordResetConfirmDTO]) -> MessageResponseDTO:
        """Validate reset token and update user password."""
        user_id = decode_user_id(parsed_body.uid)
        user = User.objects.filter(id=user_id, is_active=True).first()

        if not user or not password_reset_token_generator.check_token(user, parsed_body.token):
            raise domain_exception_to_dmr_error(
                ValidationException("Reset token is invalid, expired, or already used.")
            )

        if len(parsed_body.new_password) < 8:
            raise domain_exception_to_dmr_error(
                ValidationException("New password must contain at least 8 characters.")
            )

        user.set_password(parsed_body.new_password)
        # Update last_login to immediately invalidate the HMAC token
        user.last_login = timezone.now()
        user.save()

        log_user_action(
            self.request,
            action="PASSWORD_RESET_COMPLETE",
            user_profile=user.profile,
            target_type="USER",
            target_id=str(user.id),
        )

        return MessageResponseDTO(
            message=(
                "Password has been successfully updated. Please log in with your new credentials."
            )
        )


class PasswordChangeController(Controller[MsgspecSerializer]):
    """Update password for an authenticated user verifying current credentials."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    @modify(status_code=HTTPStatus.OK)
    def post(self, parsed_body: Body[PasswordChangeDTO]) -> MessageResponseDTO:
        """Verify current password and persist new password."""
        if not self.request.user.check_password(parsed_body.current_password):
            raise domain_exception_to_dmr_error(
                ValidationException("Current password does not match.")
            )

        if len(parsed_body.new_password) < 8:
            raise domain_exception_to_dmr_error(
                ValidationException("New password must contain at least 8 characters.")
            )

        self.request.user.set_password(parsed_body.new_password)
        self.request.user.save()

        log_user_action(
            self.request,
            action="PASSWORD_CHANGE",
            user_profile=self.request.profile,
            target_type="USER",
            target_id=str(self.request.user.id),
        )

        return MessageResponseDTO(message="Password changed successfully.")


class CurrentUserMeController(Controller[MsgspecSerializer]):
    """Fetch current authenticated identity details."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    def get(self) -> CurrentUserResponseDTO:
        """Return authenticated user and linked profile UUID."""
        return CurrentUserResponseDTO(
            user=UserSummaryDTO(
                id=str(self.request.user.id),
                username=self.request.user.username,
                email=self.request.user.email,
            ),
            profile_id=str(self.request.profile.id),
        )
