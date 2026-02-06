"""
Voting service for inter-round parameter voting (MRL and RTM).

Handles voting windows, vote casting, vote counting, and parameter changes.
"""

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from typing import Dict, Optional
import math

from core.models import Round, Vote, User, Discussion, PlatformConfig, Response
from core.services.invite_service import InviteService


class VotingService:
    """Inter-round voting logic for parameter changes"""

    @staticmethod
    def start_voting_window(round: Round) -> None:
        """
        Start voting window after round ends.

        - Set round.status = 'voting'
        - Voting window duration = round.final_mrp_minutes
        - Create Vote records for eligible voters
        - Send notifications
        """
        with transaction.atomic():
            round.status = "voting"
            round.end_time = timezone.now()
            round.save()

            # Notifications are handled by the calling task/view
            # Vote records are created on-demand when users vote

    @staticmethod
    def get_eligible_voters(round: Round) -> QuerySet[User]:
        """
        Get eligible voters for a round.

        Eligible voters:
        - Discussion initiator
        - All active participants who responded in this round
        """
        # Get users who posted in this round
        responders = User.objects.filter(responses__round=round).distinct()

        # Get discussion initiator
        initiator = round.discussion.initiator

        # Combine (union) both sets
        eligible = User.objects.filter(
            id__in=list(responders.values_list("id", flat=True)) + [initiator.id]
        ).distinct()

        return eligible

    @staticmethod
    def _award_voting_credits(round_obj: Round, voter: User) -> bool:
        """
        Award voting credits to a user if they haven't received them this round.

        Credits are awarded ONCE per voting session regardless of how many votes cast.
        Uses Round.voting_credits_awarded to track who has received credits.

        Args:
            round_obj: The Round instance for current voting session
            voter: User who cast a vote

        Returns:
            bool: True if credits awarded, False if already awarded this session
        """
        # Early return if already awarded
        awarded_user_ids = round_obj.voting_credits_awarded or []
        if voter.id in awarded_user_ids:
            return False

        # Award credits
        InviteService.earn_invite_from_vote(voter)

        # Track that credits were awarded
        if round_obj.voting_credits_awarded is None:
            round_obj.voting_credits_awarded = []
        round_obj.voting_credits_awarded.append(voter.id)
        round_obj.save(update_fields=['voting_credits_awarded'])

        return True

    @staticmethod
    def cast_parameter_vote(
        user: User, round: Round, mrl_vote: str, rtm_vote: str
    ) -> Vote:
        """
        Cast vote for parameter changes.

        - Validate user is eligible voter
        - Create or update Vote record
        - Return vote
        """
        # Validate eligible
        eligible_voters = VotingService.get_eligible_voters(round)
        if user not in eligible_voters:
            raise ValueError(
                f"User {user.username} is not eligible to vote in this round"
            )

        # Validate vote values
        valid_choices = ["increase", "no_change", "decrease"]
        if mrl_vote not in valid_choices or rtm_vote not in valid_choices:
            raise ValueError(f"Invalid vote choice. Must be one of: {valid_choices}")

        # Create or update vote
        vote, created = Vote.objects.update_or_create(
            round=round,
            user=user,
            defaults={
                "mrl_vote": mrl_vote,
                "rtm_vote": rtm_vote,
            },
        )

        # Award voting credits
        VotingService._award_voting_credits(round, user)

        return vote

    @staticmethod
    def count_votes(round: Round, parameter: str) -> Dict:
        """
        Count votes for a parameter (mrl or rtm).

        Returns: {
            'increase': count,
            'no_change': count,
            'decrease': count,
            'not_voted': count,
            'total_eligible': count,
            'majority_needed': count
        }
        """
        if parameter not in ["mrl", "rtm"]:
            raise ValueError(f"Invalid parameter: {parameter}")

        eligible_voters = VotingService.get_eligible_voters(round)
        total_eligible = eligible_voters.count()

        # Get all votes for this round
        votes = Vote.objects.filter(round=round)

        # Count votes for the parameter
        vote_field = f"{parameter}_vote"
        increase = votes.filter(**{vote_field: "increase"}).count()
        no_change = votes.filter(**{vote_field: "no_change"}).count()
        decrease = votes.filter(**{vote_field: "decrease"}).count()

        voted_count = votes.count()
        not_voted = total_eligible - voted_count

        # Majority needed (simple majority of eligible voters)
        majority_needed = math.ceil(total_eligible / 2) + 1

        return {
            "increase": increase,
            "no_change": no_change,
            "decrease": decrease,
            "not_voted": not_voted,
            "total_eligible": total_eligible,
            "majority_needed": majority_needed,
        }

    @staticmethod
    def resolve_vote(round: Round, parameter: str) -> str:
        """
        Resolve vote with simple majority of eligible voters.

        - Abstentions count as 'no_change'
        - Ties (50/50) -> 'no_change' wins
        - Returns: 'increase', 'no_change', 'decrease'
        """
        counts = VotingService.count_votes(round, parameter)

        # Add abstentions to no_change
        effective_no_change = counts["no_change"] + counts["not_voted"]

        # Find the winner
        vote_totals = {
            "increase": counts["increase"],
            "no_change": effective_no_change,
            "decrease": counts["decrease"],
        }

        # Get max vote count
        max_votes = max(vote_totals.values())
        winners = [k for k, v in vote_totals.items() if v == max_votes]

        # If tie, no_change wins
        if len(winners) > 1:
            if "no_change" in winners:
                return "no_change"
            # If tie between increase and decrease (unlikely), default to no_change
            return "no_change"

        return winners[0]

    @staticmethod
    def apply_parameter_change(
        discussion: Discussion, parameter: str, change: str, config: PlatformConfig
    ) -> None:
        """
        Apply voted parameter change.

        - Get increment percentage from config (default 20%)
        - Calculate new value
        - Validate against min/max bounds
        - Update discussion
        """
        if parameter not in ["mrl", "rtm"]:
            raise ValueError(f"Invalid parameter: {parameter}")

        if change == "no_change":
            return  # No change needed

        increment_pct = config.voting_increment_percentage / 100.0

        if parameter == "mrl":
            current_value = discussion.max_response_length_chars

            if change == "increase":
                new_value = int(current_value * (1 + increment_pct))
            else:  # decrease
                new_value = int(current_value * (1 - increment_pct))

            # Clamp to bounds
            new_value = max(config.mrl_min_chars, min(new_value, config.mrl_max_chars))
            discussion.max_response_length_chars = new_value

        elif parameter == "rtm":
            current_value = discussion.response_time_multiplier

            if change == "increase":
                new_value = current_value * (1 + increment_pct)
            else:  # decrease
                new_value = current_value * (1 - increment_pct)

            # Clamp to bounds
            new_value = max(config.rtm_min, min(new_value, config.rtm_max))
            discussion.response_time_multiplier = new_value

        discussion.save()

    @staticmethod
    def close_voting_window(round: Round, config: PlatformConfig) -> None:
        """
        Close voting window and process results.

        - Count votes for MRL and RTM
        - Resolve each vote
        - Apply parameter changes
        - Update round status to 'completed'
        """
        with transaction.atomic():
            # Resolve votes
            mrl_result = VotingService.resolve_vote(round, "mrl")
            rtm_result = VotingService.resolve_vote(round, "rtm")

            # Apply changes
            VotingService.apply_parameter_change(
                round.discussion, "mrl", mrl_result, config
            )
            VotingService.apply_parameter_change(
                round.discussion, "rtm", rtm_result, config
            )

            # Update round status
            round.status = "completed"
            round.save()

            # Next round creation is handled by MultiRoundService

    @staticmethod
    def record_join_request_vote(round_obj, voter, join_request, approve):
        """
        Record a vote on a pending join request.

        Args:
            round_obj: Current Round instance
            voter: User casting the vote
            join_request: JoinRequest instance being voted on
            approve: bool, True to approve, False to deny

        Returns:
            JoinRequestVote: The created vote

        Raises:
            ValidationError: If voter already voted on this request in this round
        """
        from core.models import JoinRequestVote
        from django.core.exceptions import ValidationError

        # Check for existing vote
        existing = JoinRequestVote.objects.filter(
            round=round_obj,
            voter=voter,
            join_request=join_request
        ).exists()

        if existing:
            raise ValidationError(f"User {voter.username} already voted on this join request")

        # Create vote
        vote = JoinRequestVote.objects.create(
            round=round_obj,
            voter=voter,
            join_request=join_request,
            approve=approve
        )

        # Award voting credits
        VotingService._award_voting_credits(round_obj, voter)

        return vote

    @staticmethod
    def get_join_request_vote_counts(round_obj, join_request):
        """
        Get vote counts for a join request in current round.

        Args:
            round_obj: Current Round instance
            join_request: JoinRequest instance

        Returns:
            dict: {'approve': int, 'deny': int, 'total': int}
        """
        from core.models import JoinRequestVote

        votes = JoinRequestVote.objects.filter(
            round=round_obj,
            join_request=join_request
        )

        approve_count = votes.filter(approve=True).count()
        deny_count = votes.filter(approve=False).count()

        return {
            'approve': approve_count,
            'deny': deny_count,
            'total': approve_count + deny_count
        }

    @staticmethod
    def determine_winning_mrl(round_obj):
        """
        Determine the new MRL value after voting.

        Args:
            round_obj: The Round that just ended voting

        Returns:
            int: The new max_response_length_chars value
        """
        config = PlatformConfig.objects.get(pk=1)
        discussion = round_obj.discussion

        # Resolve vote
        mrl_result = VotingService.resolve_vote(round_obj, "mrl")

        if mrl_result == "no_change":
            return discussion.max_response_length_chars

        increment_pct = config.voting_increment_percentage / 100.0
        current_value = discussion.max_response_length_chars

        if mrl_result == "increase":
            new_value = int(current_value * (1 + increment_pct))
        else:  # decrease
            new_value = int(current_value * (1 - increment_pct))

        # Clamp to bounds
        new_value = max(config.mrl_min_chars, min(new_value, config.mrl_max_chars))
        return new_value

    @staticmethod
    def determine_winning_rtm(round_obj):
        """
        Determine the new RTM value after voting.

        Args:
            round_obj: The Round that just ended voting

        Returns:
            float: The new response_time_multiplier value
        """
        config = PlatformConfig.objects.get(pk=1)
        discussion = round_obj.discussion

        # Resolve vote
        rtm_result = VotingService.resolve_vote(round_obj, "rtm")

        if rtm_result == "no_change":
            return discussion.response_time_multiplier

        increment_pct = config.voting_increment_percentage / 100.0
        current_value = discussion.response_time_multiplier

        if rtm_result == "increase":
            new_value = current_value * (1 + increment_pct)
        else:  # decrease
            new_value = current_value * (1 - increment_pct)

        # Clamp to bounds
        new_value = max(config.rtm_min, min(new_value, config.rtm_max))
        return new_value

    @staticmethod
    def process_join_request_votes(round_obj):
        """
        Process all pending join requests based on votes cast in this round.

        Approval requires >50% of votes (strict majority).
        Requests without majority stay pending for next round.

        Args:
            round_obj: The Round that just ended voting

        Returns:
            dict: {'approved': [list of requests], 'denied': [list of requests], 'pending': [list of requests]}
        """
        from core.models import JoinRequest
        from core.services.join_request import JoinRequestService

        discussion = round_obj.discussion
        pending_requests = JoinRequest.objects.filter(
            discussion=discussion,
            status='pending'
        )

        results = {
            'approved': [],
            'denied': [],
            'pending': []
        }

        for request in pending_requests:
            vote_counts = VotingService.get_join_request_vote_counts(round_obj, request)

            if vote_counts['total'] == 0:
                # No votes cast, stays pending
                results['pending'].append(request)
                continue

            # Calculate approval percentage
            approval_rate = vote_counts['approve'] / vote_counts['total']

            if approval_rate > 0.5:  # Strict majority (>50%)
                # Approve request
                JoinRequestService.approve_request(request, approved_by=None)  # System approval
                results['approved'].append(request)
            elif approval_rate < 0.5:  # Clear denial
                # Deny request
                JoinRequestService.decline_request(request, approver=None)  # System denial
                results['denied'].append(request)
            else:  # Exactly 50% - stays pending
                results['pending'].append(request)

        return results
