"""
Onboarding and join request API endpoints.

Handles tutorial, suggested discussions, and join requests.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.db.models import Count
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.services.onboarding import OnboardingService
from core.services.join_request import JoinRequestService
from core.models import Discussion, JoinRequest
from core.api.serializers import (
    TutorialStepSerializer,
    DiscussionSummarySerializer,
    JoinRequestCreateSerializer,
    JoinRequestSerializer,
    JoinRequestActionSerializer,
)

# Onboarding endpoints


@extend_schema(
    responses={200: TutorialStepSerializer(many=True)},
    description="Get onboarding tutorial steps",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tutorial_steps(request):
    """
    Get onboarding tutorial content.

    GET /api/onboarding/tutorial/
    """
    steps = OnboardingService.get_tutorial_steps()
    serializer = TutorialStepSerializer(steps, many=True)

    return Response(serializer.data)


@extend_schema(
    responses={200: OpenApiResponse(description="Tutorial marked complete")},
    description="Mark tutorial as completed",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_tutorial(request):
    """
    Mark tutorial as completed for user.

    POST /api/onboarding/tutorial/complete/
    """
    OnboardingService.mark_tutorial_complete(request.user)

    return Response({"message": "Tutorial completed", "completed": True})


@extend_schema(
    responses={200: DiscussionSummarySerializer(many=True)},
    description="Get suggested discussions for new users",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def suggested_discussions(request):
    """
    Get curated discussions for new users.

    GET /api/onboarding/suggested-discussions/
    """
    discussions = OnboardingService.get_suggested_discussions(request.user)

    # Annotate with counts
    discussions = discussions.annotate(
        participant_count=Count("participants"),
        response_count=Count("rounds__responses"),
    )

    serializer = DiscussionSummarySerializer(discussions, many=True)

    return Response(serializer.data)


# Join request endpoints


@extend_schema(
    request=JoinRequestCreateSerializer,
    responses={
        200: JoinRequestSerializer,
        400: OpenApiResponse(description="Cannot create request"),
    },
    description="Request to join a discussion",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_join_request(request, discussion_id):
    """
    Create join request for discussion.

    POST /api/discussions/{discussion_id}/join-request/
    """
    serializer = JoinRequestCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    message = serializer.validated_data.get("message", "")

    try:
        discussion = Discussion.objects.get(id=discussion_id)
    except Discussion.DoesNotExist:
        return Response(
            {"error": "Discussion not found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        join_request = JoinRequestService.create_request(
            discussion, request.user, message
        )

        response_serializer = JoinRequestSerializer(join_request)

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    responses={200: JoinRequestSerializer(many=True)},
    description="Get pending join requests for discussion",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discussion_join_requests(request, discussion_id):
    """
    Get join requests for discussion.

    GET /api/discussions/{discussion_id}/join-requests/
    """
    try:
        discussion = Discussion.objects.get(id=discussion_id)
    except Discussion.DoesNotExist:
        return Response(
            {"error": "Discussion not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check if user is participant (has permission to view)
    from core.models import DiscussionParticipant

    is_participant = DiscussionParticipant.objects.filter(
        discussion=discussion, user=request.user, role="active"
    ).exists()

    if not is_participant:
        return Response(
            {"error": "Only participants can view join requests"},
            status=status.HTTP_403_FORBIDDEN,
        )

    pending = JoinRequest.objects.filter(
        discussion=discussion, status="pending"
    ).select_related("requester", "approver")

    serializer = JoinRequestSerializer(pending, many=True)

    return Response({"pending": serializer.data})


@extend_schema(
    request=JoinRequestActionSerializer,
    responses={
        200: OpenApiResponse(description="Request approved"),
        400: OpenApiResponse(description="Cannot approve request"),
    },
    description="Approve join request",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_join_request(request, request_id):
    """
    Approve join request.

    POST /api/join-requests/{request_id}/approve/
    """
    try:
        join_request = JoinRequest.objects.get(id=request_id)
    except JoinRequest.DoesNotExist:
        return Response(
            {"error": "Join request not found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        participant = JoinRequestService.approve_request(join_request, request.user)

        return Response(
            {"message": "Join request approved", "participant_id": str(participant.id)},
            status=status.HTTP_200_OK,
        )

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    request=JoinRequestActionSerializer,
    responses={
        200: OpenApiResponse(description="Request declined"),
        400: OpenApiResponse(description="Cannot decline request"),
    },
    description="Decline join request",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decline_join_request(request, request_id):
    """
    Decline join request.

    POST /api/join-requests/{request_id}/decline/
    """
    serializer = JoinRequestActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    response_message = serializer.validated_data.get("response_message", "")

    try:
        join_request = JoinRequest.objects.get(id=request_id)
    except JoinRequest.DoesNotExist:
        return Response(
            {"error": "Join request not found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        JoinRequestService.decline_request(join_request, request.user, response_message)

        return Response({"message": "Join request declined"}, status=status.HTTP_200_OK)

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
