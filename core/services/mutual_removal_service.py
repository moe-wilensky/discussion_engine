"""
Mutual removal moderation service.

Handles the mutual removal (Kamikaze Lite) system where users can remove
each other from discussions with escalating consequences.
"""

from typing import Tuple, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.models import (
    User,
    Discussion,
    Round,
    DiscussionParticipant,
    ModerationAction,
    Response,
)


class MutualRemovalService:
    """Mutual removal moderation logic"""

    @staticmethod
    def can_initiate_removal(
        initiator: User, target: User, discussion: Discussion
    ) -> Tuple[bool, str]:
        """
        Check if initiator can remove target.

        Args:
            initiator: User attempting the removal
            target: User to be removed
            discussion: Discussion context

        Returns:
            Tuple of (can_remove, reason_if_not)
        """
        # Get participant records
        try:
            initiator_participant = DiscussionParticipant.objects.get(
                discussion=discussion, user=initiator
            )
        except DiscussionParticipant.DoesNotExist:
            return False, "Initiator is not a participant in this discussion"

        try:
            target_participant = DiscussionParticipant.objects.get(
                discussion=discussion, user=target
            )
        except DiscussionParticipant.DoesNotExist:
            return False, "Target is not a participant in this discussion"

        # Both must be active participants
        if initiator_participant.role not in ["initiator", "active"]:
            return False, "You must be an active participant to initiate removal"

        if target_participant.role not in ["initiator", "active"]:
            return False, "Target must be an active participant"

        # Cannot remove yourself
        if initiator == target:
            return False, "You cannot remove yourself"

        # Check if initiator already removed target in this discussion
        existing_removal = ModerationAction.objects.filter(
            discussion=discussion,
            action_type="mutual_removal",
            initiator=initiator,
            target=target,
        ).exists()

        if existing_removal:
            return False, "You have already removed this user in this discussion"

        # Check if initiator has already initiated 3 removals (would become permanent)
        if initiator_participant.removal_count >= 3:
            return (
                False,
                "You have reached the maximum number of removals and are a permanent observer",
            )

        return True, ""

    @staticmethod
    def get_removal_count(user: User, discussion: Discussion) -> int:
        """
        Count how many removals user has initiated in this discussion.

        Args:
            user: User to check
            discussion: Discussion context

        Returns:
            Number of removals initiated
        """
        try:
            participant = DiscussionParticipant.objects.get(
                discussion=discussion, user=user
            )
            return participant.removal_count
        except DiscussionParticipant.DoesNotExist:
            return 0

    @staticmethod
    def get_times_removed_count(user: User, discussion: Discussion) -> int:
        """
        Count how many times user has been removed in this discussion.

        Args:
            user: User to check
            discussion: Discussion context

        Returns:
            Number of times removed
        """
        try:
            participant = DiscussionParticipant.objects.get(
                discussion=discussion, user=user
            )
            return participant.times_removed
        except DiscussionParticipant.DoesNotExist:
            return 0

    @staticmethod
    @transaction.atomic
    def initiate_removal(
        initiator: User, target: User, discussion: Discussion, current_round: Round
    ) -> ModerationAction:
        """
        Execute mutual removal.

        Args:
            initiator: User initiating the removal
            target: User being removed
            discussion: Discussion context
            current_round: Current round

        Returns:
            ModerationAction record

        Raises:
            ValidationError: If removal cannot be performed
        """
        # Validate can initiate removal
        can_remove, reason = MutualRemovalService.can_initiate_removal(
            initiator, target, discussion
        )
        if not can_remove:
            raise ValidationError(reason)

        # Get participant records with select_for_update to prevent race conditions
        initiator_participant = DiscussionParticipant.objects.select_for_update().get(
            discussion=discussion, user=initiator
        )
        target_participant = DiscussionParticipant.objects.select_for_update().get(
            discussion=discussion, user=target
        )

        # Check if either user has already posted in current round
        initiator_posted = Response.objects.filter(
            round=current_round, user=initiator
        ).exists()
        target_posted = Response.objects.filter(
            round=current_round, user=target
        ).exists()

        # Move both to temporary observer
        initiator_participant.role = "temporary_observer"
        initiator_participant.observer_reason = "mutual_removal"
        initiator_participant.observer_since = timezone.now()
        initiator_participant.posted_in_round_when_removed = initiator_posted
        initiator_participant.removal_count += 1

        target_participant.role = "temporary_observer"
        target_participant.observer_reason = "mutual_removal"
        target_participant.observer_since = timezone.now()
        target_participant.posted_in_round_when_removed = target_posted
        target_participant.times_removed += 1

        # Check escalation - if 3rd removal, make permanent observer
        initiator_is_permanent = False
        target_is_permanent = False

        if initiator_participant.removal_count >= 3:
            initiator_participant.role = "permanent_observer"
            initiator_is_permanent = True
            # Reset platform invites
            initiator.platform_invites_acquired = 0
            initiator.platform_invites_used = 0
            initiator.platform_invites_banked = 0
            initiator.save()

        if target_participant.times_removed >= 3:
            target_participant.role = "permanent_observer"
            target_is_permanent = True
            # Reset platform invites
            target.platform_invites_acquired = 0
            target.platform_invites_used = 0
            target.platform_invites_banked = 0
            target.save()

        initiator_participant.save()
        target_participant.save()

        # Create ModerationAction record
        moderation_action = ModerationAction.objects.create(
            discussion=discussion,
            action_type="mutual_removal",
            initiator=initiator,
            target=target,
            round_occurred=current_round,
            is_permanent=target_is_permanent,
        )

        # Send notifications (will be implemented in NotificationService)
        from core.services.notification_service import NotificationService

        NotificationService.send_mutual_removal_notification(
            initiator, target, discussion, initiator_is_permanent, target_is_permanent
        )

        # Check if escalation warning needed
        if (
            initiator_participant.removal_count < 3
            and initiator_participant.removal_count > 0
        ):
            NotificationService.send_escalation_warning(
                initiator, discussion, initiator_participant.removal_count
            )
        if (
            target_participant.times_removed < 3
            and target_participant.times_removed > 0
        ):
            NotificationService.send_escalation_warning(
                target, discussion, target_participant.times_removed
            )

        # Check if round should end (no active participants left)
        active_count = discussion.participants.filter(
            role__in=["initiator", "active"]
        ).count()

        if active_count == 0:
            # Archive discussion - no active participants
            discussion.status = "archived"
            discussion.save(update_fields=["status"])

        return moderation_action

    @staticmethod
    def check_escalation(user: User, discussion: Discussion) -> str:
        """
        Check escalation status.

        Args:
            user: User to check
            discussion: Discussion context

        Returns:
            'none', 'warning', or 'permanent'
        """
        try:
            participant = DiscussionParticipant.objects.get(
                discussion=discussion, user=user
            )

            if participant.removal_count >= 3:
                return "permanent"
            elif participant.removal_count >= 1:
                return "warning"
            else:
                return "none"

        except DiscussionParticipant.DoesNotExist:
            return "none"
