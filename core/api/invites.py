"""
Invite system API endpoints.

Handles platform and discussion invites, sending, accepting, and tracking.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.services.invite_service import InviteService
from core.models import User, Discussion, Invite, PlatformConfig
from core.api.serializers import (
    UserInviteStatsSerializer,
    PlatformInviteCreateSerializer,
    PlatformInviteResponseSerializer,
    PlatformInviteAcceptSerializer,
    DiscussionInviteSendSerializer,
    DiscussionInviteResponseSerializer,
    InviteSerializer,
)


@extend_schema(
    responses={200: UserInviteStatsSerializer},
    description="Get current user's invite statistics",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_invites(request):
    """
    Get authenticated user's invite metrics.

    GET /api/invites/me/
    """
    user = request.user
    config = PlatformConfig.objects.get(pk=1)

    total_responses = user.responses.count()
    responses_needed = max(0, config.responses_to_unlock_invites - total_responses)

    can_send_platform = (
        user.platform_invites_banked > 0
        and total_responses >= config.responses_to_unlock_invites
    )
    can_send_discussion = (
        user.discussion_invites_banked > 0
        and total_responses >= config.responses_to_unlock_invites
    )

    data = {
        "platform_invites": {
            "acquired": user.platform_invites_acquired,
            "used": user.platform_invites_used,
            "banked": user.platform_invites_banked,
            "can_send": can_send_platform,
            "responses_needed_to_unlock": responses_needed,
        },
        "discussion_invites": {
            "acquired": user.discussion_invites_acquired,
            "used": user.discussion_invites_used,
            "banked": user.discussion_invites_banked,
            "can_send": can_send_discussion,
            "responses_needed_to_unlock": responses_needed,
        },
        "total_responses": total_responses,
    }

    serializer = UserInviteStatsSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    return Response(serializer.data)


@extend_schema(
    request=PlatformInviteCreateSerializer,
    responses={
        200: PlatformInviteResponseSerializer,
        400: OpenApiResponse(description="Cannot send invite"),
    },
    description="Generate platform invite code",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_platform_invite(request):
    """
    Send platform invite (generate code).

    POST /api/invites/platform/send/
    """
    try:
        invite, invite_code = InviteService.send_platform_invite(request.user)

        # In production, this would be the actual app URL
        invite_url = f"https://platform.com/join/{invite_code}"

        return Response(
            {
                "invite_code": invite_code,
                "invite_url": invite_url,
                "invite_id": str(invite.id),
            },
            status=status.HTTP_200_OK,
        )

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=PlatformInviteAcceptSerializer,
    responses={
        200: OpenApiResponse(description="Invite accepted"),
        400: OpenApiResponse(description="Invalid invite code"),
    },
    description="Accept platform invite (used during registration)",
)
@api_view(["POST"])
@permission_classes([AllowAny])
def accept_platform_invite(request):
    """
    Accept platform invite.

    POST /api/invites/platform/accept/

    Note: This is typically called during registration flow,
    not as a standalone endpoint.
    """
    serializer = PlatformInviteAcceptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    invite_code = serializer.validated_data["invite_code"]

    invite = InviteService.get_invite_by_code(invite_code)

    if not invite or invite.status != "sent":
        return Response(
            {"error": "Invalid or already used invite code"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {"message": "Invite code valid", "inviter": invite.inviter.username},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    request=DiscussionInviteSendSerializer,
    responses={
        200: DiscussionInviteResponseSerializer,
        400: OpenApiResponse(description="Cannot send invite"),
    },
    description="Send discussion invite to user",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_discussion_invite(request):
    """
    Send discussion invite to specific user.

    POST /api/invites/discussion/send/
    """
    serializer = DiscussionInviteSendSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    discussion_id = serializer.validated_data["discussion_id"]
    invitee_id = serializer.validated_data["invitee_user_id"]

    try:
        discussion = Discussion.objects.get(id=discussion_id)
        invitee = User.objects.get(id=invitee_id)
    except (Discussion.DoesNotExist, User.DoesNotExist) as e:
        return Response(
            {"error": "Discussion or user not found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        invite = InviteService.send_discussion_invite(request.user, discussion, invitee)

        return Response(
            {
                "invite_id": str(invite.id),
                "invitee": invitee.username,
                "discussion": discussion.topic_headline,
            },
            status=status.HTTP_200_OK,
        )

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    responses={200: InviteSerializer(many=True)},
    description="Get invites received by current user",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def received_invites(request):
    """
    Get invites received by authenticated user.

    GET /api/invites/received/
    """
    pending = Invite.objects.filter(invitee=request.user, status="sent").select_related(
        "inviter", "discussion"
    )

    accepted = Invite.objects.filter(
        invitee=request.user, status="accepted"
    ).select_related("inviter", "discussion")

    declined = Invite.objects.filter(
        invitee=request.user, status="declined"
    ).select_related("inviter", "discussion")

    return Response(
        {
            "pending": InviteSerializer(pending, many=True).data,
            "accepted": InviteSerializer(accepted, many=True).data,
            "declined": InviteSerializer(declined, many=True).data,
        }
    )


@extend_schema(
    responses={
        200: OpenApiResponse(description="Invite accepted"),
        400: OpenApiResponse(description="Cannot accept invite"),
    },
    description="Accept a discussion invite",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def accept_invite(request, invite_id):
    """
    Accept discussion invite.

    POST /api/invites/{invite_id}/accept/
    """
    try:
        invite = Invite.objects.get(id=invite_id)
    except Invite.DoesNotExist:
        return Response({"error": "Invite not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        InviteService.accept_invite(invite, request.user)

        return Response(
            {
                "message": "Invite accepted",
                "discussion_id": (
                    str(invite.discussion.id) if invite.discussion else None
                ),
            },
            status=status.HTTP_200_OK,
        )

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    responses={
        200: OpenApiResponse(description="Invite declined"),
        400: OpenApiResponse(description="Cannot decline invite"),
    },
    description="Decline a discussion invite",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decline_invite(request, invite_id):
    """
    Decline discussion invite.

    POST /api/invites/{invite_id}/decline/
    """
    try:
        invite = Invite.objects.get(id=invite_id)
    except Invite.DoesNotExist:
        return Response({"error": "Invite not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        InviteService.decline_invite(invite, request.user)

        return Response({"message": "Invite declined"}, status=status.HTTP_200_OK)

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    responses={200: UserInviteStatsSerializer},
    description="Get public invite metrics for any user",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def user_invite_metrics(request, user_id):
    """
    Get public invite metrics for a user.

    GET /api/users/{user_id}/invite-metrics/
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check invite formula: acquired should equal used + banked
    platform_penalized = user.platform_invites_acquired != (
        user.platform_invites_used + user.platform_invites_banked
    )
    discussion_penalized = user.discussion_invites_acquired != (
        user.discussion_invites_used + user.discussion_invites_banked
    )

    is_penalized = platform_penalized or discussion_penalized

    return Response(
        {
            "platform_invites": {
                "acquired": user.platform_invites_acquired,
                "used": user.platform_invites_used,
                "banked": user.platform_invites_banked,
                "can_send": user.platform_invites_banked > 0,
            },
            "discussion_invites": {
                "acquired": user.discussion_invites_acquired,
                "used": user.discussion_invites_used,
                "banked": user.discussion_invites_banked,
                "can_send": user.discussion_invites_banked > 0,
            },
            "is_penalized": is_penalized,
        }
    )
