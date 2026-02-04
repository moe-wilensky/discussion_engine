"""
Moderation voting service for vote-based removal system.

Handles removal votes, vote counting, and permanent observer status.
"""

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from typing import Dict, List

from core.models import (
    Round,
    RemovalVote,
    User,
    DiscussionParticipant,
    PlatformConfig,
    ModerationAction,
)


class ModerationVotingService:
    """Vote-based removal system"""

    @staticmethod
    def get_eligible_targets(round: Round, voter: User = None) -> QuerySet[User]:
        """
        Get all active participants in round (eligible removal targets).

        Excludes the voter themselves when specified.
        """
        # Get active participants in this discussion
        active_participants = DiscussionParticipant.objects.filter(
            discussion=round.discussion, role__in=["initiator", "active"]
        )

        # Get users who responded in this round
        responders = User.objects.filter(responses__round=round).distinct()

        if voter:
            # Exclude the voter themselves
            responders = responders.exclude(id=voter.id)

        return responders

    @staticmethod
    def cast_removal_vote(
        voter: User, round: Round, targets: List[User]
    ) -> List[RemovalVote]:
        """
        Cast vote to remove one or more users.

        - Validate voter is eligible (responded in round)
        - Can vote for multiple targets
        - Create RemovalVote records
        """
        # Validate voter participated in this round
        if not round.responses.filter(user=voter).exists():
            raise ValueError(f"User {voter.username} did not participate in this round")

        votes_cast = []

        with transaction.atomic():
            for target in targets:
                # Don't allow voting for yourself
                if target.id == voter.id:
                    continue

                # Validate target participated
                if not round.responses.filter(user=target).exists():
                    continue

                # Create or update vote
                vote, created = RemovalVote.objects.update_or_create(
                    round=round,
                    voter=voter,
                    target=target,
                    defaults={"voted_at": timezone.now()},
                )
                votes_cast.append(vote)

        return votes_cast

    @staticmethod
    def count_removal_votes(round: Round, target: User) -> Dict:
        """
        Count votes against a target.

        Returns: {
            'votes_for_removal': count,
            'total_eligible_voters': count,
            'percentage': float,
            'threshold': float,
            'will_be_removed': bool
        }
        """
        # Get all participants who responded in this round (eligible voters)
        eligible_voters = User.objects.filter(responses__round=round).distinct()
        total_eligible = eligible_voters.count()

        # Count votes against this target
        votes_for_removal = RemovalVote.objects.filter(
            round=round, target=target
        ).count()

        # Calculate percentage
        percentage = (
            (votes_for_removal / total_eligible * 100) if total_eligible > 0 else 0
        )

        # Get threshold from config
        config = PlatformConfig.load()
        threshold = config.vote_based_removal_threshold * 100  # Convert to percentage

        will_be_removed = percentage >= threshold

        return {
            "votes_for_removal": votes_for_removal,
            "total_eligible_voters": total_eligible,
            "percentage": percentage,
            "threshold": threshold,
            "will_be_removed": will_be_removed,
        }

    @staticmethod
    def resolve_removal_votes(round: Round, config: PlatformConfig) -> List[User]:
        """
        Resolve removal votes after voting window closes.

        - For each active participant
        - Count votes against them
        - If votes >= threshold: permanent observer
        - Reset platform_invites_acquired to 0 for removed users
        - Update DiscussionParticipant role to 'permanent_observer'
        - Log ModerationAction
        - Returns list of removed users
        """
        removed_users = []

        # Get all users who received removal votes
        targets = User.objects.filter(removal_votes_received__round=round).distinct()

        with transaction.atomic():
            for target in targets:
                vote_info = ModerationVotingService.count_removal_votes(round, target)

                if vote_info["will_be_removed"]:
                    # Get participant record
                    try:
                        participant = DiscussionParticipant.objects.get(
                            discussion=round.discussion, user=target
                        )
                    except DiscussionParticipant.DoesNotExist:
                        continue

                    # Update to permanent observer
                    participant.role = "permanent_observer"
                    participant.observer_since = timezone.now()
                    participant.observer_reason = "vote_based_removal"
                    participant.save()

                    # Reset platform invites
                    target.platform_invites_acquired = 0
                    target.platform_invites_banked = 0
                    target.save()

                    # Log moderation action
                    # Use the user with most votes as symbolic "initiator"
                    voters = RemovalVote.objects.filter(
                        round=round, target=target
                    ).values_list("voter", flat=True)

                    if voters:
                        symbolic_initiator = User.objects.get(id=voters[0])
                        ModerationAction.objects.create(
                            discussion=round.discussion,
                            action_type="vote_based_removal",
                            initiator=symbolic_initiator,
                            target=target,
                            round_occurred=round,
                            is_permanent=True,
                        )

                    removed_users.append(target)

        return removed_users
