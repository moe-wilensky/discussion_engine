"""
Response service for submission and editing.

Handles response submission, editing with budget tracking, and draft saving.
"""

import difflib
from typing import Tuple, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import (
    User,
    Round,
    Response,
    ResponseEdit,
    DraftResponse,
    PlatformConfig,
    DiscussionParticipant,
)
from core.services.invite_service import InviteService
from core.services.round_service import RoundService


class ResponseService:
    """Response submission and editing logic."""

    @staticmethod
    def can_respond(user: User, round: Round) -> Tuple[bool, str]:
        """
        Check if user can respond in this round.

        Checks:
        - Is active participant
        - Has not responded this round
        - If returning from observer: wait period elapsed
        - Round is in_progress
        - If Phase 2: within MRP

        Args:
            user: User attempting to respond
            round: Round to respond in

        Returns:
            Tuple of (can_respond, reason_if_not)
        """
        # Check if round is in progress
        if round.status != "in_progress":
            return False, "Round is not in progress"

        # Check if user is a participant
        try:
            participant = DiscussionParticipant.objects.get(
                discussion=round.discussion, user=user
            )
        except DiscussionParticipant.DoesNotExist:
            return False, "Not a participant in this discussion"

        # Check if user is active or can rejoin
        if participant.role not in ["initiator", "active"]:
            if participant.role == "temporary_observer":
                if participant.can_rejoin():
                    # Allow to respond and will be reactivated
                    pass
                else:
                    wait_end = participant.get_wait_period_end()
                    if wait_end:
                        return False, f"Cannot rejoin until {wait_end}"
                    return False, "Cannot rejoin as temporary observer"
            else:
                return False, f"Cannot respond as {participant.role}"

        # Check if already responded this round
        if round.responses.filter(user=user).exists():
            return False, "Already responded in this round"

        # Check MRP if in Phase 2
        config = PlatformConfig.load()
        if not RoundService.is_phase_1(round, config):
            if RoundService.is_mrp_expired(round):
                return False, "MRP has expired"

        return True, ""

    @staticmethod
    def submit_response(user: User, round: Round, content: str) -> Response:
        """
        Submit a response to a round.

        Actions:
        - Validate can_respond
        - Validate character count ≤ MRL
        - Calculate time_since_previous_minutes
        - Create Response
        - Recalculate MRP if Phase 2
        - Earn invites
        - Check if round should end
        - Track first participation (if from invite)

        Args:
            user: User submitting response
            round: Round to respond in
            content: Response content

        Returns:
            Created Response instance

        Raises:
            ValidationError: If validation fails
        """
        can_respond, reason = ResponseService.can_respond(user, round)
        if not can_respond:
            raise ValidationError(reason)

        # Validate character count
        char_count = len(content)
        if char_count > round.discussion.max_response_length_chars:
            raise ValidationError(
                f"Response exceeds maximum length of {round.discussion.max_response_length_chars} characters"
            )

        config = PlatformConfig.load()

        with transaction.atomic():
            # Calculate time since previous response
            last_response = round.responses.order_by("-created_at").first()

            if last_response:
                time_diff = timezone.now() - last_response.created_at
                time_since_previous = time_diff.total_seconds() / 60  # minutes
            else:
                # First response in round
                time_diff = timezone.now() - round.start_time
                time_since_previous = time_diff.total_seconds() / 60  # minutes

            # Create response
            response = Response.objects.create(
                round=round,
                user=user,
                content=content,
                character_count=char_count,
                time_since_previous_minutes=time_since_previous,
            )

            # Reactivate participant if they were a temporary observer
            participant = DiscussionParticipant.objects.get(
                discussion=round.discussion, user=user
            )

            if participant.role == "temporary_observer":
                participant.role = "active"
                participant.observer_since = None
                participant.observer_reason = None
                participant.save()

            # Recalculate MRP if in Phase 2
            if not RoundService.is_phase_1(round, config):
                new_mrp = RoundService.calculate_mrp(round, config)
                round.final_mrp_minutes = new_mrp
                round.save()
            else:
                # Check if we just transitioned to Phase 2
                if not RoundService.is_phase_1(round, config):
                    # Just transitioned, calculate initial MRP
                    new_mrp = RoundService.calculate_mrp(round, config)
                    round.final_mrp_minutes = new_mrp
                    round.save()

            # Earn invites
            InviteService.earn_invite_from_response(user)

            # Track first participation if from invite
            invites = round.discussion.invites.filter(
                invitee=user, status="accepted", first_participation_at__isnull=True
            )
            for invite in invites:
                invite.first_participation_at = timezone.now()
                invite.save()

            # Check if round should end
            if RoundService.should_end_round(round):
                RoundService.end_round(round)

            # Broadcast response posted via WebSocket
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync

                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"discussion_{round.discussion.id}",
                        {
                            "type": "new_response",
                            "response_id": response.id,
                            "author": user.username,
                            "round_number": round.round_number,
                            "response_number": round.responses.count(),
                        },
                    )
            except Exception as e:
                # Don't fail response creation if WebSocket broadcast fails
                import logging
                logging.error(f"Failed to broadcast response via WebSocket: {e}")

        return response

    @staticmethod
    def can_edit(
        user: User, response: Response, config: PlatformConfig
    ) -> Tuple[bool, str]:
        """
        Check if response can be edited.

        Checks:
        - Response belongs to user
        - Round still in_progress (not locked)
        - Edit count < config.response_edit_limit (default 2)
        - Characters changed budget remaining (20% rule)

        Args:
            user: User attempting to edit
            response: Response to edit
            config: PlatformConfig instance

        Returns:
            Tuple of (can_edit, reason_if_not)
        """
        if response.user != user:
            return False, "Can only edit your own responses"

        if response.is_locked:
            return False, "Response is locked (round ended)"

        if response.round.status != "in_progress":
            return False, "Cannot edit after round ends"

        if response.edit_count >= config.response_edit_limit:
            return False, f"Maximum {config.response_edit_limit} edits reached"

        # Check character change budget
        budget = ResponseService.calculate_edit_budget(response, config)
        if budget <= 0:
            return (
                False,
                f"Maximum {config.response_edit_percentage}% character change reached",
            )

        return True, ""

    @staticmethod
    def calculate_edit_budget(response: Response, config: PlatformConfig) -> int:
        """
        Calculate remaining character change budget.

        Budget = (original_length * edit_percentage / 100) - already_changed

        Args:
            response: Response to calculate budget for
            config: PlatformConfig instance

        Returns:
            Remaining character budget
        """
        max_changeable = (
            response.character_count * config.response_edit_percentage
        ) // 100
        remaining = max_changeable - response.characters_changed_total
        return max(0, remaining)

    @staticmethod
    def calculate_characters_changed(old_content: str, new_content: str) -> int:
        """
        Calculate number of characters changed between two strings.

        Uses difflib to count actual changes (insertions + deletions).

        Args:
            old_content: Original content
            new_content: New content

        Returns:
            Number of characters changed
        """
        # Use SequenceMatcher to get edit operations
        matcher = difflib.SequenceMatcher(None, old_content, new_content)

        chars_changed = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "delete":
                chars_changed += i2 - i1
            elif tag == "insert":
                chars_changed += j2 - j1
            elif tag == "replace":
                chars_changed += max(i2 - i1, j2 - j1)

        return chars_changed

    @staticmethod
    def edit_response(
        user: User, response: Response, new_content: str, config: PlatformConfig
    ) -> Response:
        """
        Edit an existing response.

        Actions:
        - Validate can_edit
        - Calculate characters changed
        - Check against budget
        - Create ResponseEdit record
        - Update Response

        Args:
            user: User editing the response
            response: Response to edit
            new_content: New content
            config: PlatformConfig instance

        Returns:
            Updated Response instance

        Raises:
            ValidationError: If validation fails
        """
        can_edit, reason = ResponseService.can_edit(user, response, config)
        if not can_edit:
            raise ValidationError(reason)

        # Calculate characters changed
        chars_changed = ResponseService.calculate_characters_changed(
            response.content, new_content
        )

        # Check budget
        budget = ResponseService.calculate_edit_budget(response, config)
        if chars_changed > budget:
            raise ValidationError(
                f"Edit would change {chars_changed} characters, "
                f"but only {budget} characters remaining in budget"
            )

        with transaction.atomic():
            # Create edit record
            ResponseEdit.objects.create(
                response=response,
                edit_number=response.edit_count + 1,
                previous_content=response.content,
                new_content=new_content,
                characters_changed=chars_changed,
            )

            # Update response
            response.content = new_content
            response.character_count = len(new_content)
            response.edit_count += 1
            response.characters_changed_total += chars_changed
            response.last_edited_at = timezone.now()
            response.save()

        return response

    @staticmethod
    def save_draft(
        user: User, round: Round, content: str, reason: str
    ) -> DraftResponse:
        """
        Save a draft response.

        Drafts are saved when:
        - MRP expires while user is composing
        - User manually saves
        - Round ends while user is composing

        Args:
            user: User saving draft
            round: Round for the draft
            content: Draft content
            reason: Reason for saving ('mrp_expired', 'user_saved', 'round_ended')

        Returns:
            Created DraftResponse instance
        """
        draft = DraftResponse.objects.create(
            discussion=round.discussion,
            round=round,
            user=user,
            content=content,
            saved_reason=reason,
        )
        return draft

    @staticmethod
    def get_response_number(response: Response) -> int:
        """
        Get the position number of a response in its round.

        Args:
            response: Response to get number for

        Returns:
            Response number (1-indexed)
        """
        earlier_responses = response.round.responses.filter(
            created_at__lt=response.created_at
        ).count()
        return earlier_responses + 1
