"""
Round service for managing round lifecycle and MRP calculation.

Implements the Median Response Period (MRP) calculation algorithm
and handles round progression including Phase 1/2 transitions.
"""

import statistics
from typing import Optional, List
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from core.models import (
    Round,
    Discussion,
    Response,
    PlatformConfig,
    DiscussionParticipant,
)


class RoundService:
    """Round lifecycle management and MRP calculation."""

    @staticmethod
    def start_round_1(discussion: Discussion) -> Round:
        """
        Initialize Round 1 for a new discussion.

        Args:
            discussion: Discussion to start round for

        Returns:
            Created Round instance
        """
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            start_time=timezone.now(),
        )
        return round

    @staticmethod
    def is_phase_1(round: Round, config: PlatformConfig) -> bool:
        """
        Check if round is still in Phase 1 (free-form responses).

        Phase 1 ends when N responses are posted, where:
        N = min(config.n_responses_before_mrp, invited_participants_count)

        Args:
            round: Round to check
            config: PlatformConfig instance

        Returns:
            True if in Phase 1, False if in Phase 2
        """
        response_count = round.responses.count()

        # Get count of invited participants (initiator + active)
        invited_count = round.discussion.participants.filter(
            role__in=["initiator", "active"]
        ).count()

        # N is minimum of config setting and invited count
        n_threshold = min(config.n_responses_before_mrp, invited_count)

        return response_count < n_threshold

    @staticmethod
    def check_phase_1_timeout(round: Round, config: PlatformConfig) -> bool:
        """
        Check if Phase 1 timeout reached (default 30 days).

        If fewer than N responses after timeout: archive discussion.

        Args:
            round: Round to check
            config: PlatformConfig instance

        Returns:
            True if timeout reached, False otherwise
        """
        if not RoundService.is_phase_1(round, config):
            return False

        timeout_days = config.round_1_phase_1_timeout_days
        elapsed = timezone.now() - round.start_time

        if elapsed.days >= timeout_days:
            # Check if we have enough responses
            response_count = round.responses.count()
            invited_count = round.discussion.participants.filter(
                role__in=["initiator", "active"]
            ).count()
            n_threshold = min(config.n_responses_before_mrp, invited_count)

            if response_count < n_threshold:
                # Archive the discussion
                with transaction.atomic():
                    discussion = round.discussion
                    discussion.status = "archived"
                    discussion.archived_at = timezone.now()
                    discussion.save()
                return True

        return False

    @staticmethod
    def calculate_mrp(round: Round, config: PlatformConfig) -> float:
        """
        Calculate the Median Response Period (MRP) for this round.

        Algorithm (spec Section 5.2):
        1. Get response times based on mrp_calculation_scope:
           - 'current_round': times from this round only
           - 'last_X_rounds': times from previous X rounds
           - 'all_rounds': all times from all rounds
        2. Adjust times: if t < MRM, set t = MRM
        3. Calculate median of adjusted times
        4. MRP = median × RTM
        5. Minimum MRP = MRM × RTM

        Args:
            round: Round to calculate MRP for
            config: PlatformConfig instance

        Returns:
            MRP in minutes

        Example:
            Response times: [10, 60, 40]
            MRM = 30, RTM = 2
            Adjusted times: [30, 60, 40]  (10 -> 30)
            Median = 40
            MRP = 40 × 2 = 80 minutes
        """
        mrm = round.discussion.min_response_time_minutes
        rtm = round.discussion.response_time_multiplier

        # Get response times based on scope
        response_times = []

        if config.mrp_calculation_scope == "current_round":
            # Only this round
            times = list(
                round.responses.filter(
                    time_since_previous_minutes__isnull=False
                ).values_list("time_since_previous_minutes", flat=True)
            )
            response_times.extend(times)

        elif config.mrp_calculation_scope == "last_X_rounds":
            # Get last X rounds including current
            rounds = Round.objects.filter(
                discussion=round.discussion, round_number__lte=round.round_number
            ).order_by("-round_number")[: config.mrp_calculation_x_rounds]

            for r in rounds:
                times = list(
                    r.responses.filter(
                        time_since_previous_minutes__isnull=False
                    ).values_list("time_since_previous_minutes", flat=True)
                )
                response_times.extend(times)

        else:  # 'all_rounds'
            # All rounds up to and including current
            rounds = Round.objects.filter(
                discussion=round.discussion, round_number__lte=round.round_number
            )

            for r in rounds:
                times = list(
                    r.responses.filter(
                        time_since_previous_minutes__isnull=False
                    ).values_list("time_since_previous_minutes", flat=True)
                )
                response_times.extend(times)

        if not response_times:
            # No response times yet, use minimum MRP
            return float(mrm * rtm)

        # Step 2: Adjust times - if t < MRM, set t = MRM
        adjusted_times = [max(t, mrm) for t in response_times]

        # Step 3: Calculate median
        median_time = statistics.median(adjusted_times)

        # Step 4: MRP = median × RTM
        mrp = median_time * rtm

        # Step 5: Ensure minimum MRP = MRM × RTM
        min_mrp = mrm * rtm
        mrp = max(mrp, min_mrp)

        return float(mrp)

    @staticmethod
    def is_mrp_expired(round: Round) -> bool:
        """
        Check if MRP has expired since last response.

        Args:
            round: Round to check

        Returns:
            True if MRP expired, False otherwise
        """
        if round.status != "in_progress":
            return False

        if not round.final_mrp_minutes:
            return False

        # Get last response time
        last_response = round.responses.order_by("-created_at").first()

        if not last_response:
            # No responses yet, check against round start time
            elapsed_minutes = (timezone.now() - round.start_time).total_seconds() / 60
            return elapsed_minutes >= round.final_mrp_minutes

        # Check time since last response
        elapsed_minutes = (
            timezone.now() - last_response.created_at
        ).total_seconds() / 60
        return elapsed_minutes >= round.final_mrp_minutes

    @staticmethod
    def get_mrp_deadline(round: Round) -> Optional[timezone.datetime]:
        """
        Calculate when MRP expires.

        Args:
            round: Round to calculate deadline for

        Returns:
            Datetime when MRP expires, or None if not applicable
        """
        if not round.final_mrp_minutes or round.status != "in_progress":
            return None

        last_response = round.responses.order_by("-created_at").first()

        if not last_response:
            # No responses yet, deadline from round start
            return round.start_time + timedelta(minutes=round.final_mrp_minutes)

        # Deadline from last response
        return last_response.created_at + timedelta(minutes=round.final_mrp_minutes)

    @staticmethod
    def handle_mrp_expiration(round: Round) -> None:
        """
        Handle MRP expiration when no response is submitted in time.

        Actions:
        - Move all non-responders to observer status
        - If ≤1 total response: archive discussion
        - Otherwise: end round, start inter-round voting

        Args:
            round: Round that expired
        """
        with transaction.atomic():
            # Get all participants who haven't responded
            responders = set(round.responses.values_list("user_id", flat=True))
            participants = DiscussionParticipant.objects.filter(
                discussion=round.discussion, role__in=["initiator", "active"]
            )

            for participant in participants:
                if participant.user_id not in responders:
                    # Check if they posted in this round (before becoming observer)
                    posted_in_round = round.responses.filter(
                        user=participant.user
                    ).exists()

                    # Move to temporary observer
                    participant.role = "temporary_observer"
                    participant.observer_since = timezone.now()
                    participant.observer_reason = "mrp_expired"
                    participant.posted_in_round_when_removed = posted_in_round
                    participant.removal_count += 1
                    # Skip invite credits on return if didn't post
                    participant.skip_invite_credits_on_return = not posted_in_round
                    participant.save()

            # Check if we should archive (≤1 response total OR ≤1 active participant)
            total_responses = round.responses.count()
            active_count = DiscussionParticipant.objects.filter(
                discussion=round.discussion, role__in=["initiator", "active"]
            ).count()
            
            if total_responses <= 1 or active_count <= 1:
                discussion = round.discussion
                discussion.status = "archived"
                discussion.archived_at = timezone.now()
                discussion.save()
            else:
                # End the round
                RoundService.end_round(round)

    @staticmethod
    def should_end_round(round: Round) -> bool:
        """
        Check if round should end.

        Round ends when:
        - All invited participants responded, OR
        - MRP expired with no response

        Args:
            round: Round to check

        Returns:
            True if round should end
        """
        if round.status != "in_progress":
            return False

        # Check MRP expiration
        if RoundService.is_mrp_expired(round):
            return True

        # Check if all active participants have responded
        active_participants = DiscussionParticipant.objects.filter(
            discussion=round.discussion, role__in=["initiator", "active"]
        )

        for participant in active_participants:
            if not round.responses.filter(user=participant.user).exists():
                return False

        return True

    @staticmethod
    def end_round(round: Round) -> None:
        """
        End the current round.

        Actions:
        - Set end_time
        - Calculate and store final_mrp_minutes
        - Lock all responses (is_locked = True)
        - Set status = 'voting'

        Args:
            round: Round to end
        """
        with transaction.atomic():
            config = PlatformConfig.load()

            # Calculate final MRP if not already set
            if not round.final_mrp_minutes:
                round.final_mrp_minutes = RoundService.calculate_mrp(round, config)

            # Set end time
            round.end_time = timezone.now()

            # Set status to voting
            round.status = "voting"
            round.save()

            # Lock all responses in this round
            round.responses.update(is_locked=True)

    @staticmethod
    def get_phase_info(round: Round, config: PlatformConfig) -> dict:
        """
        Get information about current phase.

        Args:
            round: Round to get info for
            config: PlatformConfig instance

        Returns:
            Dictionary with phase information
        """
        is_phase_1 = RoundService.is_phase_1(round, config)
        response_count = round.responses.count()

        invited_count = round.discussion.participants.filter(
            role__in=["initiator", "active"]
        ).count()
        n_threshold = min(config.n_responses_before_mrp, invited_count)

        info = {
            "phase": 1 if is_phase_1 else 2,
            "responses_count": response_count,
            "responses_needed_for_phase_2": n_threshold,
        }

        if not is_phase_1:
            # Phase 2 - include MRP info
            if not round.final_mrp_minutes:
                round.final_mrp_minutes = RoundService.calculate_mrp(round, config)
                round.save()

            info["mrp_minutes"] = round.final_mrp_minutes
            info["mrp_deadline"] = RoundService.get_mrp_deadline(round)
        else:
            info["mrp_minutes"] = None
            info["mrp_deadline"] = None

        return info
