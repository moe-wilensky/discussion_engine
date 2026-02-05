"""
API endpoints for voting functionality.

Handles parameter voting, removal voting, and observer status.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response as APIResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from core.models import Discussion, Round, DiscussionParticipant, User
from core.services.voting_service import VotingService
from core.services.moderation_voting_service import ModerationVotingService
from core.services.observer_service import ObserverService


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def voting_status(request, discussion_id, round_number):
    """
    GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/status/

    Returns voting window status and user eligibility.
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)
    round = get_object_or_404(Round, discussion=discussion, round_number=round_number)

    # Check if voting window is open
    voting_window_open = round.status == "voting"

    # Calculate window close time
    window_closes_at = None
    time_remaining = None
    if voting_window_open and round.end_time and round.final_mrp_minutes:
        window_closes_at = round.end_time + timedelta(minutes=round.final_mrp_minutes)
        if timezone.now() < window_closes_at:
            remaining = window_closes_at - timezone.now()
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            time_remaining = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        else:
            voting_window_open = False

    # Check if user is eligible
    eligible_voters = VotingService.get_eligible_voters(round)
    user_is_eligible = request.user in eligible_voters

    # Check if user has voted
    user_has_voted_parameters = round.votes.filter(user=request.user).exists()
    user_has_voted_removal = round.removal_votes.filter(voter=request.user).exists()

    # Count votes
    eligible_voters_count = eligible_voters.count()
    votes_cast_count = round.votes.count()

    return APIResponse(
        {
            "voting_window_open": voting_window_open,
            "window_closes_at": (
                window_closes_at.isoformat() if window_closes_at else None
            ),
            "time_remaining": time_remaining,
            "user_is_eligible": user_is_eligible,
            "user_has_voted_parameters": user_has_voted_parameters,
            "user_has_voted_removal": user_has_voted_removal,
            "eligible_voters_count": eligible_voters_count,
            "votes_cast_count": votes_cast_count,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def parameter_results(request, discussion_id, round_number):
    """
    GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/parameter-results/

    Returns current parameter voting results.
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)
    round = get_object_or_404(Round, discussion=discussion, round_number=round_number)

    mrl_counts = VotingService.count_votes(round, "mrl")
    rtm_counts = VotingService.count_votes(round, "rtm")

    # Calculate current winners (with abstentions as no_change)
    mrl_winner = VotingService.resolve_vote(round, "mrl")
    rtm_winner = VotingService.resolve_vote(round, "rtm")

    # Check if will pass (winner has majority)
    mrl_will_pass = (
        mrl_counts[mrl_winner]
        + (mrl_counts["not_voted"] if mrl_winner == "no_change" else 0)
    ) >= mrl_counts["majority_needed"]
    rtm_will_pass = (
        rtm_counts[rtm_winner]
        + (rtm_counts["not_voted"] if rtm_winner == "no_change" else 0)
    ) >= rtm_counts["majority_needed"]

    return APIResponse(
        {
            "mrl": {
                **mrl_counts,
                "current_winner": mrl_winner,
                "will_pass": mrl_will_pass,
            },
            "rtm": {
                **rtm_counts,
                "current_winner": rtm_winner,
                "will_pass": rtm_will_pass,
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cast_parameter_vote(request, discussion_id, round_number):
    """
    POST /api/discussions/{discussion_id}/rounds/{round_number}/voting/parameters/

    Cast parameter vote (MRL and RTM).
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)
    round = get_object_or_404(Round, discussion=discussion, round_number=round_number)

    # Validate voting window is open
    if round.status != "voting":
        return APIResponse(
            {"error": "Voting window is not open"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Get vote choices
    mrl_vote = request.data.get("mrl_vote")
    rtm_vote = request.data.get("rtm_vote")

    if not mrl_vote or not rtm_vote:
        return APIResponse(
            {"error": "Both mrl_vote and rtm_vote are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        vote = VotingService.cast_parameter_vote(
            request.user, round, mrl_vote, rtm_vote
        )

        # Get updated results
        mrl_counts = VotingService.count_votes(round, "mrl")
        rtm_counts = VotingService.count_votes(round, "rtm")

        return APIResponse(
            {
                "vote_recorded": True,
                "current_results": {
                    "mrl": mrl_counts,
                    "rtm": rtm_counts,
                },
            }
        )
    except ValueError as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def removal_targets(request, discussion_id, round_number):
    """
    GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/removal-targets/

    Returns eligible targets for removal voting.
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)
    round = get_object_or_404(Round, discussion=discussion, round_number=round_number)

    targets = ModerationVotingService.get_eligible_targets(round, request.user)

    targets_data = []
    for target in targets:
        # Get response count
        responses_this_round = round.responses.filter(user=target).count()

        # Get invite metrics
        participant = DiscussionParticipant.objects.filter(
            discussion=discussion, user=target
        ).first()

        targets_data.append(
            {
                "user_id": str(target.id),
                "username": target.username,
                "responses_this_round": responses_this_round,
                "invite_metrics": {
                    "platform_invites_banked": target.platform_invites_banked,
                    "discussion_invites_banked": target.discussion_invites_banked,
                },
            }
        )

    return APIResponse({"eligible_targets": targets_data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cast_removal_vote(request, discussion_id, round_number):
    """
    POST /api/discussions/{discussion_id}/rounds/{round_number}/voting/removal/

    Cast removal vote for one or more targets.
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)
    round = get_object_or_404(Round, discussion=discussion, round_number=round_number)

    # Validate voting window is open
    if round.status != "voting":
        return APIResponse(
            {"error": "Voting window is not open"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Get target user IDs
    target_user_ids = request.data.get("target_user_ids", [])

    if not target_user_ids:
        return APIResponse(
            {"error": "At least one target_user_id required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get target users
    targets = User.objects.filter(id__in=target_user_ids)

    try:
        votes = ModerationVotingService.cast_removal_vote(
            request.user, round, list(targets)
        )

        return APIResponse(
            {"votes_cast": len(votes), "message": "Removal votes recorded"}
        )
    except ValueError as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def removal_results(request, discussion_id, round_number):
    """
    GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/removal-results/

    Returns removal voting results for all targets.
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)
    round = get_object_or_404(Round, discussion=discussion, round_number=round_number)

    # Get all users who received votes
    targets = User.objects.filter(removal_votes_received__round=round).distinct()

    targets_data = []
    for target in targets:
        vote_info = ModerationVotingService.count_removal_votes(round, target)

        targets_data.append(
            {
                "user_id": str(target.id),
                "username": target.username,
                "votes_for_removal": vote_info["votes_for_removal"],
                "total_eligible": vote_info["total_eligible_voters"],
                "percentage": vote_info["percentage"],
                "threshold": vote_info["threshold"],
                "will_be_removed": vote_info["will_be_removed"],
            }
        )

    return APIResponse({"targets": targets_data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def observer_status(request, discussion_id):
    """
    GET /api/discussions/{discussion_id}/observer-status/

    Returns observer status and rejoin eligibility for current user.
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)

    try:
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=request.user
        )
    except DiscussionParticipant.DoesNotExist:
        return APIResponse(
            {"error": "User is not a participant in this discussion"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get current round
    current_round = (
        Round.objects.filter(discussion=discussion, status="in_progress")
        .order_by("-round_number")
        .first()
    )

    can_rejoin_bool = False
    can_rejoin_reason = None
    can_rejoin_at = None
    can_rejoin_in_round = None

    if current_round:
        can_rejoin_bool, can_rejoin_reason = ObserverService.can_rejoin(
            participant, current_round
        )
        can_rejoin_at = ObserverService.get_wait_period_end(participant, current_round)

        # Determine which round user can rejoin
        if participant.role == "temporary_observer":
            # Logic based on observer reason
            if (
                participant.observer_reason == "mutual_removal"
                and not participant.posted_in_round_when_removed
            ):
                # Same round after 1 MRP
                can_rejoin_in_round = current_round.round_number
            else:
                # Next round after 1 MRP
                can_rejoin_in_round = current_round.round_number + 1

    return APIResponse(
        {
            "user_role": participant.role,
            "observer_since": (
                participant.observer_since.isoformat()
                if participant.observer_since
                else None
            ),
            "observer_reason": participant.observer_reason,
            "posted_before_removal": participant.posted_in_round_when_removed,
            "can_rejoin": can_rejoin_bool,
            "can_rejoin_at": can_rejoin_at.isoformat() if can_rejoin_at else None,
            "current_round": current_round.round_number if current_round else None,
            "can_rejoin_in_round": can_rejoin_in_round,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rejoin_discussion(request, discussion_id):
    """
    POST /api/discussions/{discussion_id}/rejoin/

    Rejoin discussion as active participant.
    """
    discussion = get_object_or_404(Discussion, id=discussion_id)

    try:
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=request.user
        )
    except DiscussionParticipant.DoesNotExist:
        return APIResponse(
            {"error": "User is not a participant in this discussion"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check if user is already active
    if participant.role in ["initiator", "active"]:
        return APIResponse(
            {"error": "Already an active participant"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get current round
    current_round = (
        Round.objects.filter(discussion=discussion, status="in_progress")
        .order_by("-round_number")
        .first()
    )

    if not current_round:
        return APIResponse(
            {"error": "No active round available"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Check if user can rejoin
    can_rejoin, reason = ObserverService.can_rejoin(participant, current_round)

    if not can_rejoin:
        # Determine appropriate status code based on reason
        if reason == "permanent":
            error_message = "You are a permanent observer and cannot rejoin"
            error_status = status.HTTP_403_FORBIDDEN
        elif reason.startswith("wait_"):
            # Extract minutes from reason
            parts = reason.split("_")
            try:
                minutes_remaining = float(parts[1])
                error_message = (
                    f"You must wait {minutes_remaining:.1f} more minutes before rejoining"
                )
            except (ValueError, IndexError):
                error_message = "You cannot rejoin at this time"
            error_status = status.HTTP_403_FORBIDDEN
        elif reason == "must_wait_for_next_round":
            error_message = "You must wait until the next round to rejoin"
            error_status = status.HTTP_403_FORBIDDEN
        else:
            error_message = f"Cannot rejoin: {reason}"
            error_status = status.HTTP_403_FORBIDDEN

        return APIResponse({"error": error_message}, status=error_status)

    try:
        ObserverService.rejoin_as_active(participant)

        # Send WebSocket notification to all participants
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"discussion_{discussion.id}",
                {
                    "type": "new_participant",
                    "user_id": request.user.id,
                    "username": request.user.username,
                    "role": "active",
                    "rejoined": True,
                },
            )

        return APIResponse(
            {
                "rejoined": True,
                "new_role": "active",
                "current_round": current_round.round_number,
            }
        )
    except ValueError as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
