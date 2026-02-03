"""
Discussion service for creating and managing discussions.

Handles discussion creation, retrieval, and duplicate checking.
"""

from typing import List, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import QuerySet

from core.models import (
    User, Discussion, DiscussionParticipant, PlatformConfig, Round
)
from core.services.discussion_presets import DiscussionPreset
from core.services.invite_service import InviteService


class DiscussionService:
    """Core discussion business logic."""
    
    @staticmethod
    def create_discussion(
        initiator: User,
        headline: str,
        details: str,
        mrm: int,
        rtm: float,
        mrl: int,
        initial_invites: Optional[List[User]] = None
    ) -> Discussion:
        """
        Create new discussion with validation.
        
        Args:
            initiator: User creating the discussion
            headline: Discussion headline (topic)
            details: Discussion details/description
            mrm: Minimum Response Minutes
            rtm: Response Time Multiplier
            mrl: Maximum Response Length in characters
            initial_invites: List of users to invite initially
            
        Returns:
            Created Discussion instance
            
        Raises:
            ValidationError: If validation fails
        """
        config = PlatformConfig.load()
        initial_invites = initial_invites or []
        
        # Validate headline length
        if len(headline) > config.max_headline_length:
            raise ValidationError(
                f"Headline cannot exceed {config.max_headline_length} characters"
            )
        
        # Validate details length
        if len(details) > config.max_topic_length:
            raise ValidationError(
                f"Details cannot exceed {config.max_topic_length} characters"
            )
        
        # Validate parameters
        is_valid, error_msg = DiscussionPreset.validate_parameters(mrm, rtm, mrl, config)
        if not is_valid:
            raise ValidationError(error_msg)
        
        # Check for duplicates if configured
        if not config.allow_duplicate_discussions:
            if DiscussionService.check_duplicate(headline, config):
                raise ValidationError(
                    "A discussion with this headline already exists"
                )
        
        with transaction.atomic():
            # Create Discussion
            discussion = Discussion.objects.create(
                initiator=initiator,
                topic_headline=headline,
                topic_details=details,
                min_response_time_minutes=mrm,
                response_time_multiplier=rtm,
                max_response_length_chars=mrl,
                status='active'
            )
            
            # Create DiscussionParticipant for initiator
            DiscussionParticipant.objects.create(
                discussion=discussion,
                user=initiator,
                role='initiator',
                can_invite_others=True
            )
            
            # Send invites to initial participants
            for invitee in initial_invites:
                try:
                    InviteService.send_discussion_invite(
                        inviter=initiator,
                        invitee=invitee,
                        discussion=discussion
                    )
                except ValidationError:
                    # Continue if invite fails (e.g., no invites left)
                    pass
            
            # Create Round 1
            Round.objects.create(
                discussion=discussion,
                round_number=1,
                status='in_progress',
                start_time=timezone.now()
            )
            
        return discussion
    
    @staticmethod
    def get_active_discussions(user: User) -> QuerySet:
        """
        Get discussions where user is an active participant.
        
        Args:
            user: User to get discussions for
            
        Returns:
            QuerySet of discussions
        """
        return Discussion.objects.filter(
            participants__user=user,
            participants__role__in=['initiator', 'active'],
            status='active'
        ).distinct().select_related('initiator').prefetch_related('participants__user')
    
    @staticmethod
    def get_observable_discussions(user: User) -> QuerySet:
        """
        Get all discussions user can view (including as observer).
        
        Args:
            user: User to get discussions for
            
        Returns:
            QuerySet of discussions
        """
        return Discussion.objects.filter(
            participants__user=user,
            status='active'
        ).distinct().select_related('initiator').prefetch_related('participants__user')
    
    @staticmethod
    def check_duplicate(headline: str, config: PlatformConfig) -> bool:
        """
        Check if duplicate discussion exists.
        
        Args:
            headline: Discussion headline to check
            config: PlatformConfig instance
            
        Returns:
            True if duplicate exists, False otherwise
        """
        # Case-insensitive exact match on active discussions
        return Discussion.objects.filter(
            topic_headline__iexact=headline,
            status='active'
        ).exists()
    
    @staticmethod
    def get_discussion_status(discussion: Discussion, user: User) -> dict:
        """
        Get comprehensive discussion status for a user.
        
        Args:
            discussion: Discussion to get status for
            user: User requesting status
            
        Returns:
            Dictionary with discussion status information
        """
        # Get user's participation
        try:
            participation = DiscussionParticipant.objects.get(
                discussion=discussion,
                user=user
            )
        except DiscussionParticipant.DoesNotExist:
            participation = None
        
        # Get current round
        current_round = discussion.rounds.filter(
            status='in_progress'
        ).order_by('-round_number').first()
        
        config = PlatformConfig.load()
        
        # Build status dict
        status = {
            'is_participant': participation is not None,
            'role': participation.role if participation else None,
            'can_invite': participation.can_invite_others if participation else False,
        }
        
        if current_round:
            # Check if user has responded this round
            has_responded = current_round.responses.filter(user=user).exists()
            status['has_responded_this_round'] = has_responded
            
            # Check if user can respond
            from core.services.response_service import ResponseService
            can_respond, reason = ResponseService.can_respond(user, current_round)
            status['can_respond'] = can_respond
            status['can_respond_reason'] = reason if not can_respond else None
        else:
            status['has_responded_this_round'] = False
            status['can_respond'] = False
            status['can_respond_reason'] = 'No active round'
        
        return status
