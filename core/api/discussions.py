"""
Discussion API endpoints.

Handles discussion creation, retrieval, and parameter previews.
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Discussion, User, PlatformConfig
from core.api.serializers import (
    DiscussionPresetSerializer,
    PreviewParametersSerializer,
    DiscussionCreateSerializer,
    DiscussionDetailSerializer,
    RoundInfoSerializer,
)
from core.services.discussion_presets import DiscussionPreset
from core.services.discussion_service import DiscussionService
from core.services.round_service import RoundService

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_presets(request):
    """
    GET /api/discussions/presets/

    Get all available discussion presets.
    """
    presets = DiscussionPreset.get_presets()
    preset_list = list(presets.values())

    serializer = DiscussionPresetSerializer(preset_list, many=True)

    return Response({"presets": serializer.data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_parameters(request):
    """
    POST /api/discussions/preview-parameters/

    Preview discussion parameters with plain-language explanation.

    Request:
        {
            "mrm": 30,
            "rtm": 2.0,
            "mrl": 2000
        }

    Response:
        {
            "valid": true,
            "preview": "If people respond every 30 minutes...",
            "estimated_mrp_minutes": 60
        }
    """
    serializer = PreviewParametersSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    mrm = serializer.validated_data["mrm"]
    rtm = serializer.validated_data["rtm"]
    mrl = serializer.validated_data["mrl"]

    config = PlatformConfig.load()

    # Validate parameters
    is_valid, error_msg = DiscussionPreset.validate_parameters(mrm, rtm, mrl, config)

    if not is_valid:
        return Response(
            {"valid": False, "error": error_msg}, status=status.HTTP_400_BAD_REQUEST
        )

    # Generate preview
    preview_data = DiscussionPreset.preview_parameters(mrm, rtm, mrl)

    return Response({"valid": True, **preview_data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_discussion(request):
    """
    POST /api/discussions/

    Create a new discussion.

    Request:
        {
            "headline": "Should we...",
            "details": "Full topic description...",
            "preset": "thoughtful_discussion",  // OR custom parameters:
            "mrm_minutes": 30,
            "rtm": 2.0,
            "mrl_chars": 2000,
            "initial_invites": [user_id_1, user_id_2]
        }
    """
    serializer = DiscussionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data

    # Determine parameters (preset or custom)
    if data.get("preset"):
        try:
            preset = DiscussionPreset.get_preset(data["preset"])
            mrm = preset["mrm_minutes"]
            rtm = preset["rtm"]
            mrl = preset["mrl_chars"]
        except KeyError:
            return Response(
                {"error": f"Invalid preset: {data['preset']}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        # Custom parameters
        mrm = data.get("mrm_minutes")
        rtm = data.get("rtm")
        mrl = data.get("mrl_chars")

        if not all([mrm, rtm, mrl]):
            return Response(
                {
                    "error": "Must provide either preset or all custom parameters (mrm_minutes, rtm, mrl_chars)"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Get initial invites
    initial_invite_ids = data.get("initial_invites", [])
    initial_invites = []

    for user_id in initial_invite_ids:
        try:
            user = User.objects.get(id=user_id)
            initial_invites.append(user)
        except User.DoesNotExist:
            return Response(
                {"error": f"User {user_id} not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Create discussion
    try:
        discussion = DiscussionService.create_discussion(
            initiator=request.user,
            headline=data["headline"],
            details=data["details"],
            mrm=mrm,
            rtm=rtm,
            mrl=mrl,
            initial_invites=initial_invites,
        )
    except Exception as e:
        logger.exception(f"Error creating discussion: {e}")
        return Response(
            {"error": "Failed to create discussion. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get current round info
    current_round = discussion.rounds.first()
    config = PlatformConfig.load()
    phase_info = RoundService.get_phase_info(current_round, config)

    return Response(
        {
            "discussion_id": discussion.id,
            "round": {
                "round_number": current_round.round_number,
                "status": current_round.status,
                **phase_info,
            },
            "participants": [
                {"user_id": p.user.id, "username": p.user.username, "role": p.role}
                for p in discussion.participants.all()
            ],
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_discussion(request, discussion_id):
    """
    GET /api/discussions/{discussion_id}/

    Get detailed discussion information.
    """
    try:
        discussion = Discussion.objects.get(id=discussion_id)
    except Discussion.DoesNotExist:
        return Response(
            {"error": "Discussion not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Check if user is a participant
    if not discussion.participants.filter(user=request.user).exists():
        return Response(
            {"error": "Not a participant in this discussion"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Get current round
    current_round = (
        discussion.rounds.filter(status="in_progress").order_by("-round_number").first()
    )

    config = PlatformConfig.load()

    # Build response
    serializer = DiscussionDetailSerializer(discussion, context={"request": request})

    response_data = serializer.data

    # Add current round with phase info
    if current_round:
        phase_info = RoundService.get_phase_info(current_round, config)
        response_data["current_round"] = {
            "number": current_round.round_number,
            "status": current_round.status,
            **phase_info,
        }

    return Response(response_data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_discussions(request):
    """
    GET /api/discussions/

    List all discussions for the current user.

    Query params:
        - type: 'active' (default) or 'observable'
    """
    discussion_type = request.query_params.get("type", "active")

    if discussion_type == "active":
        discussions = DiscussionService.get_active_discussions(request.user)
    else:
        discussions = DiscussionService.get_observable_discussions(request.user)

    serializer = DiscussionDetailSerializer(
        discussions, many=True, context={"request": request}
    )

    return Response({"discussions": serializer.data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_discussion_states(request):
    """
    GET /api/discussions/my-states/

    Get current state of all discussions for dashboard.
    Returns discussion cards with status, urgency, and action labels.
    """
    from django.utils import timezone
    from datetime import timedelta
    from core.models import DiscussionParticipant, Response as ResponseModel, Round
    
    user = request.user
    
    # Get all participations
    participations = DiscussionParticipant.objects.filter(
        user=user
    ).select_related('discussion')
    
    discussions = []
    for participation in participations:
        disc = participation.discussion
        
        # Get the latest active round
        current_round = Round.objects.filter(
            discussion=disc
        ).order_by('-round_number').first()
        
        # Determine UI status and action
        ui_status = 'waiting'
        ui_icon = '⏸️'
        action_label = 'Waiting for others'
        urgency_level = 'low'
        deadline_iso = None
        
        if participation.role == 'active':
            if current_round and current_round.status == 'in_progress':
                has_responded = ResponseModel.objects.filter(
                    round=current_round,
                    user=user
                ).exists()
                
                if not has_responded:
                    ui_status = 'active-needs-response'
                    ui_icon = '✍️'
                    action_label = 'Your response needed'
                    
                    if current_round.end_time:
                        deadline_iso = current_round.end_time.isoformat()
                        remaining = current_round.end_time - timezone.now()
                        if remaining.total_seconds() > 0:
                            minutes = int(remaining.total_seconds() / 60)
                            if minutes < 10:
                                urgency_level = 'high'
                            elif minutes < 60:
                                urgency_level = 'medium'
            
            elif current_round and current_round.status == 'voting':
                has_voted = current_round.votes.filter(user=user).exists()
                
                if not has_voted:
                    ui_status = 'voting-available'
                    ui_icon = '🗳️'
                    action_label = 'Voting available'
                    urgency_level = 'medium'
                    
                    if current_round.end_time and current_round.final_mrp_minutes:
                        voting_deadline = current_round.end_time + timedelta(
                            minutes=current_round.final_mrp_minutes
                        )
                        deadline_iso = voting_deadline.isoformat()
        
        elif participation.role == 'observer':
            ui_status = 'observer'
            ui_icon = '👁️'
            action_label = 'Observing'
        
        discussions.append({
            'id': disc.id,
            'ui_status': ui_status,
            'ui_icon': ui_icon,
            'action_label': action_label,
            'urgency_level': urgency_level,
            'deadline_iso': deadline_iso,
        })
    
    return Response({
        'discussions': discussions,
        'credits': {
            'platform': float(user.platform_invites_banked),
            'discussion': float(user.discussion_invites_banked),
        }
    })

