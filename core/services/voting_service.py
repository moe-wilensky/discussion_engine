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
