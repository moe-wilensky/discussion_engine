"""
Moderation API endpoints.

Handles mutual removal and moderation status endpoints.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
import logging

from core.models import Discussion, Round, ModerationAction
from core.services.mutual_removal_service import MutualRemovalService

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mutual_removal(request, discussion_id):
    """
    Initiate mutual removal of a user.

    POST /api/discussions/{discussion_id}/mutual-removal/

    Request:
        {
            "target_user_id": "uuid"
        }

    Response:
        {
            "success": true,
            "moderation_action_id": "uuid",
            "initiator_status": "temporary_observer",
            "target_status": "permanent_observer",
            "initiator_removal_count": 1,
            "target_times_removed": 3,
            "escalation_warning": "You have initiated 1 of 3 allowed removals"
        }
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)
    target_user_id = request.data.get("target_user_id")

    if not target_user_id:
        return Response(
            {"error": "target_user_id is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Get target user
    from core.models import User

    try:
        target_user = User.objects.get(id=target_user_id)
    except User.DoesNotExist:
        return Response(
            {"error": "Target user not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Get current round
    current_round = (
        discussion.rounds.filter(status="in_progress").order_by("-round_number").first()
    )
    if not current_round:
        return Response(
            {"error": "No active round found"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Attempt mutual removal
    try:
        moderation_action = MutualRemovalService.initiate_removal(
            initiator=request.user,
            target=target_user,
            discussion=discussion,
            current_round=current_round,
        )

        # Get updated participant info
        initiator_participant = discussion.participants.get(user=request.user)
        target_participant = discussion.participants.get(user=target_user)

        # Generate escalation warning message
        escalation_warning = None
        if initiator_participant.removal_count < 3:
            escalation_warning = f"You have initiated {initiator_participant.removal_count} of 3 allowed removals"

        return Response(
            {
                "success": True,
                "moderation_action_id": str(moderation_action.id),
                "initiator_status": initiator_participant.role,
                "target_status": target_participant.role,
                "initiator_removal_count": initiator_participant.removal_count,
                "target_times_removed": target_participant.times_removed,
                "escalation_warning": escalation_warning,
            },
            status=status.HTTP_200_OK,
        )

    except ValidationError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in mutual removal: {e}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def moderation_status(request, discussion_id):
    """
    Get moderation status for current user in discussion.

    GET /api/discussions/{discussion_id}/moderation-status/

    Response:
        {
            "user_removal_count": 1,
            "user_times_removed": 0,
            "can_initiate_removal": true,
            "escalation_status": "warning",
            "moderation_history": [
                {
                    "id": "uuid",
                    "action_type": "mutual_removal",
                    "initiator": "user_id",
                    "target": "user_id",
                    "created_at": "2026-02-03T14:45:00Z",
                    "round_number": 2
                }
            ]
        }
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)

    # Get user's participant record
    try:
        participant = discussion.participants.get(user=request.user)
    except:
        return Response(
            {"error": "You are not a participant in this discussion"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get removal counts
    removal_count = MutualRemovalService.get_removal_count(request.user, discussion)
    times_removed = MutualRemovalService.get_times_removed_count(
        request.user, discussion
    )

    # Check if can initiate removal (need at least one other active participant)
    can_initiate = False
    if participant.role in ["initiator", "active"] and removal_count < 3:
        # Check if there are other active participants
        other_active = (
            discussion.participants.filter(role__in=["initiator", "active"])
            .exclude(user=request.user)
            .exists()
        )
        can_initiate = other_active

    # Get escalation status
    escalation_status = MutualRemovalService.check_escalation(request.user, discussion)

    # Get moderation history
    moderation_history = []

    # Actions where user was initiator
    initiator_actions = ModerationAction.objects.filter(
        discussion=discussion, initiator=request.user
    ).select_related("round_occurred", "target")

    # Actions where user was target
    target_actions = ModerationAction.objects.filter(
        discussion=discussion, target=request.user
    ).select_related("round_occurred", "initiator")

    all_actions = list(initiator_actions) + list(target_actions)
    all_actions.sort(key=lambda x: x.action_at, reverse=True)

    for action in all_actions:
        moderation_history.append(
            {
                "id": str(action.id),
                "action_type": action.action_type,
                "initiator": str(action.initiator.id),
                "initiator_username": action.initiator.username,
                "target": str(action.target.id),
                "target_username": action.target.username,
                "created_at": action.action_at.isoformat(),
                "round_number": action.round_occurred.round_number,
                "is_permanent": action.is_permanent,
            }
        )

    return Response(
        {
            "user_removal_count": removal_count,
            "user_times_removed": times_removed,
            "can_initiate_removal": can_initiate,
            "escalation_status": escalation_status,
            "moderation_history": moderation_history,
        },
        status=status.HTTP_200_OK,
    )
