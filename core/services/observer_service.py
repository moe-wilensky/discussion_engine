"""
Observer service for complex observer reintegration logic.

Implements nuanced rules for temporary observer status and rejoining.
"""

from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from typing import Tuple, Optional

from core.models import DiscussionParticipant, Round, User


class ObserverService:
    """Complex observer reintegration logic"""

    @staticmethod
    def move_to_observer(
        participant: DiscussionParticipant,
        reason: str,
        posted_in_round: bool = False
    ) -> None:
        """
        Move user to observer status.
        
        - Update role to 'temporary_observer'
        - Set observer_since = now
        - Set observer_reason
        - Set posted_in_round_when_removed
        """
        with transaction.atomic():
            participant.role = 'temporary_observer'
            participant.observer_since = timezone.now()
            participant.observer_reason = reason
            participant.posted_in_round_when_removed = posted_in_round
            
            if reason == 'mutual_removal':
                participant.removal_count += 1
            
            participant.save()

    @staticmethod
    def can_rejoin(
        participant: DiscussionParticipant,
        current_round: Round
    ) -> Tuple[bool, str]:
        """
        Implement nuanced reentry rules (spec Section 5.3).
        
        1. Initial invitees who never participated: Can join anytime
        2. Moved to observer via mutual removal BEFORE posting: Can rejoin same round after 1 MRP
        3. Moved to observer via mutual removal AFTER posting: Must wait until 1 MRP in NEXT round
        4. Moved to observer due to MRP expiration: Must wait until 1 MRP in NEXT round
        5. Permanent observer: Never
        
        Returns: (can_rejoin, reason_if_not)
        """
        # 5. Permanent observer
        if participant.role == 'permanent_observer':
            return False, "permanent"

        # If not an observer, can join
        if participant.role in ['initiator', 'active']:
            return True, ""

        # If not temporary observer, can't rejoin
        if participant.role != 'temporary_observer':
            return False, "unknown_status"

        if not participant.observer_since:
            return False, "no_observer_timestamp"

        # 1. Initial invitees who never participated (role is temporary_observer but no explicit removal reason yet)
        # These are users who naturally became observers without being explicitly removed
        # If they have an observer_reason, they were explicitly removed and have specific rules
        
        # Get the round when removal occurred
        removal_round = Round.objects.filter(
            discussion=participant.discussion,
            start_time__lte=participant.observer_since
        ).order_by('-start_time').first()

        if not removal_round:
            # If no round found before observer_since, assume first round
            removal_round = Round.objects.filter(
                discussion=participant.discussion
            ).order_by('round_number').first()
            
            if not removal_round:
                return False, "cannot_determine_removal_round"

        # 2. Mutual removal BEFORE posting in current round
        if participant.observer_reason == 'mutual_removal' and not participant.posted_in_round_when_removed:
            # Can rejoin same round after 1 MRP has elapsed
            if current_round.round_number == removal_round.round_number:
                # Check if 1 MRP has elapsed
                if removal_round.final_mrp_minutes:
                    elapsed_minutes = (timezone.now() - participant.observer_since).total_seconds() / 60
                    if elapsed_minutes >= removal_round.final_mrp_minutes:
                        return True, ""
                    else:
                        return False, f"wait_{removal_round.final_mrp_minutes - elapsed_minutes:.1f}_minutes"
                else:
                    return False, "mrp_not_calculated"
            elif current_round.round_number > removal_round.round_number:
                # Already in a later round, can rejoin
                return True, ""
            else:
                return False, "round_logic_error"

        # 3. Mutual removal AFTER posting in current round
        # 4. MRP expiration (didn't post in round)
        if (participant.observer_reason == 'mutual_removal' and participant.posted_in_round_when_removed) or \
           (participant.observer_reason == 'mrp_expired'):
            # Must wait until 1 MRP has elapsed in NEXT round
            next_round_number = removal_round.round_number + 1
            
            if current_round.round_number < next_round_number:
                return False, "must_wait_for_next_round"
            
            if current_round.round_number == next_round_number:
                # Check if 1 MRP has elapsed in this round
                if current_round.final_mrp_minutes:
                    # Calculate time since start of this round
                    elapsed_in_round = (timezone.now() - current_round.start_time).total_seconds() / 60
                    if elapsed_in_round >= current_round.final_mrp_minutes:
                        return True, ""
                    else:
                        return False, f"wait_{current_round.final_mrp_minutes - elapsed_in_round:.1f}_minutes_in_round_{next_round_number}"
                else:
                    return False, "mrp_not_calculated_for_next_round"
            else:
                # Already past next round, can rejoin
                return True, ""

        return False, "unknown_observer_reason"

    @staticmethod
    def get_wait_period_end(
        participant: DiscussionParticipant,
        current_round: Round
    ) -> Optional[timezone.datetime]:
        """
        Calculate when observer can rejoin based on nuanced rules.
        """
        if participant.role != 'temporary_observer' or not participant.observer_since:
            return None

        # Get the round when removal occurred
        removal_round = Round.objects.filter(
            discussion=participant.discussion,
            start_time__lte=participant.observer_since
        ).order_by('-start_time').first()

        # If no round found, use current round
        if not removal_round:
            removal_round = current_round
            
        if not removal_round or not removal_round.final_mrp_minutes:
            return None

        # Mutual removal before posting: same round + 1 MRP
        if participant.observer_reason == 'mutual_removal' and not participant.posted_in_round_when_removed:
            return participant.observer_since + timedelta(minutes=removal_round.final_mrp_minutes)

        # Mutual removal after posting or MRP expiration: next round + 1 MRP
        if (participant.observer_reason == 'mutual_removal' and participant.posted_in_round_when_removed) or \
           (participant.observer_reason == 'mrp_expired'):
            # Find next round
            next_round = Round.objects.filter(
                discussion=participant.discussion,
                round_number=removal_round.round_number + 1
            ).first()
            
            if next_round and next_round.final_mrp_minutes:
                return next_round.start_time + timedelta(minutes=next_round.final_mrp_minutes)
            else:
                # Next round not started yet
                return None

        return None

    @staticmethod
    def rejoin_as_active(participant: DiscussionParticipant) -> None:
        """
        Return observer to active status.
        
        - Validate can_rejoin
        - Update role to 'active'
        - Clear observer_since, observer_reason
        """
        # Get current round
        current_round = Round.objects.filter(
            discussion=participant.discussion,
            status='in_progress'
        ).order_by('-round_number').first()

        if not current_round:
            raise ValueError("No active round to rejoin")

        can_rejoin, reason = ObserverService.can_rejoin(participant, current_round)
        
        if not can_rejoin:
            raise ValueError(f"Cannot rejoin: {reason}")

        with transaction.atomic():
            participant.role = 'active'
            participant.observer_since = None
            participant.observer_reason = None
            participant.posted_in_round_when_removed = False
            participant.save()

    @staticmethod
    def make_permanent_observer(
        participant: DiscussionParticipant,
        reason: str
    ) -> None:
        """
        Permanent observer status.
        
        - Update role to 'permanent_observer'
        - Set observer_reason
        - Reset user.platform_invites_acquired = 0
        - Reset user.platform_invites_banked = 0
        """
        with transaction.atomic():
            participant.role = 'permanent_observer'
            participant.observer_since = timezone.now()
            participant.observer_reason = reason
            participant.save()

            # Reset platform invites
            user = participant.user
            user.platform_invites_acquired = 0
            user.platform_invites_banked = 0
            user.save()
