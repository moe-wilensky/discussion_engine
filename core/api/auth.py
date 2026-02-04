"""
Authentication API endpoints.

Handles phone-based registration, verification, and JWT token management.
"""

import logging
from datetime import timedelta

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited

from core.auth.registration import PhoneVerificationService
from core.services.invite_service import InviteService
from core.models import User, PlatformConfig
from core.api.serializers import (
    PhoneVerificationRequestSerializer,
    PhoneVerificationResponseSerializer,
    VerifyCodeSerializer,
    LoginSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema(
    request=PhoneVerificationRequestSerializer,
    responses={
        200: PhoneVerificationResponseSerializer,
        400: OpenApiResponse(description="Validation error"),
        429: OpenApiResponse(description="Too many requests"),
    },
    description="Request SMS verification code for registration",
)
@ratelimit(key='ip', rate='5/h', method='POST')
@api_view(["POST"])
@permission_classes([AllowAny])
def request_verification(request):
    """
    Request phone verification code.

    POST /api/auth/register/request-verification/
    Rate limit: 5 requests per hour per IP
    """
    # Check if rate limited
    if getattr(request, 'limited', False):
        return Response(
            {"error": "Too many verification requests. Please try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )

    serializer = PhoneVerificationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    phone_number = str(serializer.validated_data["phone_number"])

    try:
        verification_id, success, message = (
            PhoneVerificationService.send_verification_code(phone_number)
        )

        expires_at = timezone.now() + timedelta(
            minutes=PhoneVerificationService.CODE_EXPIRY_MINUTES
        )

        response_serializer = PhoneVerificationResponseSerializer(
            data={
                "verification_id": verification_id,
                "expires_at": expires_at,
                "message": message,
            }
        )
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=VerifyCodeSerializer,
    responses={
        200: OpenApiResponse(description="User created and authenticated"),
        400: OpenApiResponse(description="Invalid code or invite"),
        429: OpenApiResponse(description="Too many requests"),
    },
    description="Verify code and complete registration",
)
@ratelimit(key='ip', rate='10/h', method='POST')
@api_view(["POST"])
@permission_classes([AllowAny])
def verify_and_register(request):
    """
    Verify code and register user.

    POST /api/auth/register/verify/
    Rate limit: 10 requests per hour per IP
    """
    # Check if rate limited
    if getattr(request, 'limited', False):
        return Response(
            {"error": "Too many registration attempts. Please try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )

    serializer = VerifyCodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    verification_id = str(serializer.validated_data["verification_id"])
    code = serializer.validated_data["code"]
    invite_code = serializer.validated_data.get("invite_code", "")
    username = serializer.validated_data["username"]

    # Verify the code
    is_valid, message, phone_number = PhoneVerificationService.verify_code(
        verification_id, code
    )

    if not is_valid:
        return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

    # Handle invite code (if provided)
    invite = None
    if invite_code:
        invite = InviteService.get_invite_by_code(invite_code)
        if not invite or invite.status != "sent" or invite.invite_type != "platform":
            return Response(
                {"error": "Invalid or expired invite code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Create user
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, phone_number=phone_number
            )

            # Create notification preferences for new user
            from core.services.notification_service import NotificationService

            NotificationService.create_notification_preferences(user)

            # Accept invite if provided
            if invite:
                InviteService.accept_invite(invite, user)
            else:
                # No invite - give starting allocation
                config = PlatformConfig.objects.get(pk=1)
                user.platform_invites_acquired = config.new_user_platform_invites
                user.platform_invites_banked = config.new_user_platform_invites
                user.discussion_invites_acquired = config.new_user_discussion_invites
                user.discussion_invites_banked = config.new_user_discussion_invites
                user.save()

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            # Get invite allocation info
            config = PlatformConfig.objects.get(pk=1)
            total_responses = user.responses.count()
            responses_needed = max(
                0, config.responses_to_unlock_invites - total_responses
            )

            return Response(
                {
                    "user_id": str(user.id),
                    "username": user.username,
                    "tokens": {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                    },
                    "invite_allocation": {
                        "platform_invites": user.platform_invites_banked,
                        "discussion_invites": user.discussion_invites_banked,
                        "responses_needed_to_unlock": responses_needed,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

    except Exception as e:
        logger.exception(f"Error during user registration: {e}")
        return Response(
            {"error": "Registration failed. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    request=LoginSerializer,
    responses={
        200: PhoneVerificationResponseSerializer,
        400: OpenApiResponse(description="Invalid phone number"),
        429: OpenApiResponse(description="Too many requests"),
    },
    description="Request login verification code",
)
@ratelimit(key='ip', rate='10/h', method='POST')
@api_view(["POST"])
@permission_classes([AllowAny])
def login_request(request):
    """
    Request login verification code.

    POST /api/auth/login/
    Rate limit: 10 requests per hour per IP
    """
    # Check if rate limited
    if getattr(request, 'limited', False):
        return Response(
            {"error": "Too many login requests. Please try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )

    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    phone_number = str(serializer.validated_data["phone_number"])

    # Check if user exists
    try:
        user = User.objects.get(phone_number=phone_number)
    except User.DoesNotExist:
        return Response(
            {"error": "No account found with this phone number"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Send verification code (reuse same service, but bypass duplicate check)
    try:
        # Generate code directly for login
        from core.auth.registration import PhoneVerificationService
        import uuid
        import secrets
        from django.core.cache import cache

        # Use cryptographically secure random generation
        code_number = secrets.randbelow(1000000)
        code = f"{code_number:06d}"
        verification_id = str(uuid.uuid4())

        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"

        expiry_seconds = PhoneVerificationService.CODE_EXPIRY_MINUTES * 60
        cache.set(code_key, code, timeout=expiry_seconds)
        cache.set(phone_key, phone_number, timeout=expiry_seconds)

        # Send SMS
        from core.tasks import send_verification_sms

        send_verification_sms.delay(phone_number, code)

        expires_at = timezone.now() + timedelta(
            minutes=PhoneVerificationService.CODE_EXPIRY_MINUTES
        )

        return Response(
            {
                "verification_id": verification_id,
                "expires_at": expires_at,
                "message": "Verification code sent",
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception(f"Error sending login verification code: {e}")
        return Response(
            {"error": "Failed to send verification code. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    request=VerifyCodeSerializer,
    responses={
        200: OpenApiResponse(description="User authenticated"),
        400: OpenApiResponse(description="Invalid code"),
    },
    description="Verify login code and get tokens",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def login_verify(request):
    """
    Verify login code and return JWT tokens.

    POST /api/auth/login/verify/
    """
    verification_id = request.data.get("verification_id")
    code = request.data.get("code")

    if not verification_id or not code:
        return Response(
            {"error": "verification_id and code required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Verify code
    is_valid, message, phone_number = PhoneVerificationService.verify_code(
        verification_id, code
    )

    if not is_valid:
        return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

    # Get user
    try:
        user = User.objects.get(phone_number=phone_number)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    # Generate tokens
    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "user_id": str(user.id),
            "username": user.username,
            "tokens": {"access": str(refresh.access_token), "refresh": str(refresh)},
        },
        status=status.HTTP_200_OK,
    )
