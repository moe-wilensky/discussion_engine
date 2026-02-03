"""
Multi-round service for Round 2+ lifecycle management.

Handles round creation, termination conditions, and discussion archival.
"""

from django.db import transaction
from django.utils import timezone
from typing import Tuple, Optional

from core.models import (
    Discussion, Round, PlatformConfig, DiscussionParticipant, Response
)


class MultiRoundService:
    """Round 2+ lifecycle management"""

    @staticmethod
    def create_next_round(discussion: Discussion, previous_round: Round) -> Round:
        """
        Create next round after voting completes.
        
        - Increment round_number
        - Inherit final_mrp_minutes from previous round (or adjusted if RTM changed)
        - Set status = 'in_progress'
        - MRP regulation applies from first response (no Phase 1)
        """
        with transaction.atomic():
            # Check termination conditions first
            should_archive, reason = MultiRoundService.check_termination_conditions(
                discussion, previous_round, PlatformConfig.load()
            )
            
            if should_archive:
                MultiRoundService.archive_discussion(discussion, reason)
                return None

            # Create new round
            new_round = Round.objects.create(
                discussion=discussion,
                round_number=previous_round.round_number + 1,
                status='in_progress',
                # Inherit MRP from previous round
                # If RTM changed, it will be reflected when calculating MRP for this round
                final_mrp_minutes=previous_round.final_mrp_minutes
            )

            return new_round

    @staticmethod
    def check_termination_conditions(
        discussion: Discussion,
        round: Round,
        config: PlatformConfig
    ) -> Tuple[bool, str]:
        """
        Check if discussion should be archived.
        
        Checks (in order):
        1. All active participants became permanent observers
        2. Round received ≤1 response
        3. max_discussion_duration_days reached (if > 0)
        4. max_discussion_rounds reached (if > 0)
        5. max_discussion_responses reached (if > 0)
        
        Returns: (should_archive, reason)
        """
        # 1. Check if all active participants are permanent observers
        active_count = DiscussionParticipant.objects.filter(
            discussion=discussion,
            role__in=['initiator', 'active']
        ).count()
        
        if active_count == 0:
            return True, "All active participants became permanent observers"

        # 2. Check if round received ≤1 response
        response_count = round.responses.count()
        if response_count <= 1:
            return True, f"Round {round.round_number} received only {response_count} response(s)"

        # 3. Check duration
        if config.max_discussion_duration_days > 0:
            age_days = (timezone.now() - discussion.created_at).days
            if age_days >= config.max_discussion_duration_days:
                return True, f"Exceeded maximum duration of {config.max_discussion_duration_days} days"

        # 4. Check round count
        if config.max_discussion_rounds > 0:
            if round.round_number >= config.max_discussion_rounds:
                return True, f"Reached maximum rounds of {config.max_discussion_rounds}"

        # 5. Check total response count
        if config.max_discussion_responses > 0:
            total_responses = Response.objects.filter(round__discussion=discussion).count()
            if total_responses >= config.max_discussion_responses:
                return True, f"Reached maximum responses of {config.max_discussion_responses}"

        return False, None

    @staticmethod
    def archive_discussion(discussion: Discussion, reason: str) -> None:
        """
        Archive discussion.
        
        - Set status = 'archived'
        - Set archived_at timestamp
        - Lock all responses across all rounds
        - Log archival reason (in discussion object or separate log)
        """
        with transaction.atomic():
            discussion.status = 'archived'
            discussion.archived_at = timezone.now()
            discussion.save()

            # Lock all responses
            Response.objects.filter(
                round__discussion=discussion
            ).update(is_locked=True)

            # Archival reason could be stored in a log model
            # For now, it's implied by the archived_at timestamp
            # Notifications would be sent by the calling task
