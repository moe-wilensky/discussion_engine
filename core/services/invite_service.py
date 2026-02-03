"""
Invite system service for platform and discussion invites.

Manages invite creation, consumption, earning, and tracking.
"""

import random
import string
from typing import Optional, Tuple
from datetime import timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import User, Discussion, Invite, PlatformConfig, DiscussionParticipant


class InviteService:
    """
    Core invite business logic for platform and discussion invites.
    """
    
    INVITE_CODE_LENGTH = 8
    
    @staticmethod
    def can_send_invite(
        user: User, 
        invite_type: str
    ) -> Tuple[bool, str]:
        """
        Check if user has invites available.
        
        Args:
            user: User attempting to send invite
            invite_type: 'platform' or 'discussion'
            
        Returns:
            Tuple of (can_send, reason_if_not)
        """
        config = PlatformConfig.objects.get(pk=1)
        
        # Check responses threshold for unlocking invites
        total_responses = user.responses.count()
        if total_responses < config.responses_to_unlock_invites:
            responses_needed = config.responses_to_unlock_invites - total_responses
            return False, f"Need {responses_needed} more responses to unlock invites"
        
        # Check banked invites
        if invite_type == 'platform':
            if user.platform_invites_banked <= 0:
                return False, "No platform invites available"
        elif invite_type == 'discussion':
            if user.discussion_invites_banked <= 0:
                return False, "No discussion invites available"
        else:
            return False, "Invalid invite type"
        
        return True, ""
    
    @staticmethod
    def send_platform_invite(inviter: User) -> Invite:
        """
        Generate unique invite code for platform.
        
        Args:
            inviter: User sending the invite
            
        Returns:
            Created Invite object
            
        Raises:
            ValidationError: If user cannot send invites
        """
        can_send, reason = InviteService.can_send_invite(inviter, 'platform')
        if not can_send:
            raise ValidationError(reason)
        
        config = PlatformConfig.objects.get(pk=1)
        
        with transaction.atomic():
            # Create invite
            invite = Invite.objects.create(
                inviter=inviter,
                invite_type='platform',
                status='sent'
            )
            
            # Generate unique code and store in behavioral_flags
            invite_code = InviteService._generate_invite_code()
            if not isinstance(inviter.behavioral_flags, dict):
                inviter.behavioral_flags = {}
            
            if 'invite_codes' not in inviter.behavioral_flags:
                inviter.behavioral_flags['invite_codes'] = {}
            
            inviter.behavioral_flags['invite_codes'][invite_code] = str(invite.id)
            
            # Consume invite based on config
            if config.invite_consumption_trigger == 'sent':
                inviter.consume_invite('platform')
            
            inviter.save()
            
            # Store code in invite's behavioral flags for easy lookup
            invite.inviter.behavioral_flags.setdefault('invite_codes', {})[invite_code] = str(invite.id)
            
        return invite, invite_code
    
    @staticmethod
    def send_discussion_invite(
        inviter: User,
        discussion: Discussion,
        invitee: User
    ) -> Invite:
        """
        Invite user to specific discussion.
        
        Args:
            inviter: User sending the invite
            discussion: Discussion to invite to
            invitee: User being invited
            
        Returns:
            Created Invite object
            
        Raises:
            ValidationError: If invite cannot be sent
        """
        # Validate inviter is active participant
        if not DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=inviter,
            role='active'
        ).exists():
            raise ValidationError("Only active participants can send invites")
        
        # Check if discussion is at cap
        config = PlatformConfig.objects.get(pk=1)
        current_participants = DiscussionParticipant.objects.filter(
            discussion=discussion,
            role='active'
        ).count()
        
        if current_participants >= config.max_discussion_participants:
            raise ValidationError("Discussion is at maximum capacity")
        
        # Check if invitee already participant
        if DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=invitee
        ).exists():
            raise ValidationError("User is already a participant")
        
        # Check if pending invite exists
        if Invite.objects.filter(
            inviter=inviter,
            invitee=invitee,
            discussion=discussion,
            status='sent',
            invite_type='discussion'
        ).exists():
            raise ValidationError("Invite already pending for this user")
        
        can_send, reason = InviteService.can_send_invite(inviter, 'discussion')
        if not can_send:
            raise ValidationError(reason)
        
        with transaction.atomic():
            # Create invite
            invite = Invite.objects.create(
                inviter=inviter,
                invitee=invitee,
                invite_type='discussion',
                discussion=discussion,
                status='sent'
            )
            
            # Consume invite if configured
            config = PlatformConfig.objects.get(pk=1)
            if config.invite_consumption_trigger == 'sent':
                inviter.consume_invite('discussion')
            
            # Send notification via Celery
            from core.tasks import send_invite_notification
            send_invite_notification.delay(str(invite.id))
        
        return invite
    
    @staticmethod
    def accept_invite(invite: Invite, user: Optional[User] = None) -> User:
        """
        Accept an invite.
        
        Args:
            invite: Invite object to accept
            user: User accepting (for platform invites, this may be None initially)
            
        Returns:
            User that accepted the invite
            
        Raises:
            ValidationError: If invite cannot be accepted
        """
        if invite.status != 'sent':
            raise ValidationError("Invite has already been processed")
        
        config = PlatformConfig.objects.get(pk=1)
        
        with transaction.atomic():
            # For discussion invites
            if invite.invite_type == 'discussion':
                if not user or user.id != invite.invitee.id:
                    raise ValidationError("Invalid user for this invite")
                
                # Add user to discussion participants
                DiscussionParticipant.objects.create(
                    discussion=invite.discussion,
                    user=user,
                    role='active'
                )
                
                # Update invite
                invite.status = 'accepted'
                invite.accepted_at = timezone.now()
                invite.save()
                
                # Consume invite if configured
                if config.invite_consumption_trigger == 'accepted':
                    invite.inviter.consume_invite('discussion')
            
            # For platform invites
            elif invite.invite_type == 'platform':
                if not user:
                    raise ValidationError("User required for platform invite")
                
                # Set invitee
                invite.invitee = user
                invite.status = 'accepted'
                invite.accepted_at = timezone.now()
                invite.save()
                
                # Grant starting invites to new user
                user.platform_invites_acquired = config.new_user_platform_invites
                user.platform_invites_banked = config.new_user_platform_invites
                user.discussion_invites_acquired = config.new_user_discussion_invites
                user.discussion_invites_banked = config.new_user_discussion_invites
                user.save()
                
                # Consume invite if configured
                if config.invite_consumption_trigger == 'accepted':
                    invite.inviter.consume_invite('platform')
        
        return user
    
    @staticmethod
    def decline_invite(invite: Invite, user: User) -> None:
        """
        Decline an invite.
        
        Args:
            invite: Invite to decline
            user: User declining the invite
            
        Raises:
            ValidationError: If invite cannot be declined
        """
        if invite.status != 'sent':
            raise ValidationError("Invite has already been processed")
        
        if invite.invitee and invite.invitee.id != user.id:
            raise ValidationError("Invalid user for this invite")
        
        invite.status = 'declined'
        invite.save()
    
    @staticmethod
    def track_first_participation(user: User, discussion: Discussion) -> None:
        """
        Track when invited user first participates in discussion.
        
        Args:
            user: User who participated
            discussion: Discussion they participated in
        """
        # Find discussion invite for this user/discussion
        invite = Invite.objects.filter(
            invitee=user,
            discussion=discussion,
            invite_type='discussion',
            status='accepted',
            first_participation_at__isnull=True
        ).first()
        
        if invite:
            invite.first_participation_at = timezone.now()
            invite.save()
            
            # Consume invite if not already consumed
            config = PlatformConfig.objects.get(pk=1)
            if config.invite_consumption_trigger not in ['sent', 'accepted']:
                invite.inviter.consume_invite('discussion')
    
    @staticmethod
    def earn_invite_from_response(user: User) -> dict:
        """
        Called after each response submission to calculate earned invites.
        
        Args:
            user: User who submitted response
            
        Returns:
            Dict with earned invite counts
        """
        config = PlatformConfig.objects.get(pk=1)
        
        # Count user's total responses
        total_responses = user.responses.count()
        
        # Calculate earned platform invites
        earned_platform = total_responses // config.responses_per_platform_invite
        
        # Calculate earned discussion invites
        earned_discussion = total_responses // config.responses_per_discussion_invite
        
        # Update user's acquired and banked invites
        with transaction.atomic():
            user.refresh_from_db()
            
            platform_diff = earned_platform - user.platform_invites_acquired
            discussion_diff = earned_discussion - user.discussion_invites_acquired
            
            if platform_diff > 0:
                user.platform_invites_acquired = earned_platform
                user.platform_invites_banked += platform_diff
            
            if discussion_diff > 0:
                user.discussion_invites_acquired = earned_discussion
                user.discussion_invites_banked += discussion_diff
            
            user.save()
        
        return {
            'platform_invites_earned': platform_diff if platform_diff > 0 else 0,
            'discussion_invites_earned': discussion_diff if discussion_diff > 0 else 0,
            'total_platform': user.platform_invites_acquired,
            'total_discussion': user.discussion_invites_acquired
        }
    
    @staticmethod
    def _generate_invite_code() -> str:
        """Generate unique 8-character invite code."""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=InviteService.INVITE_CODE_LENGTH))
    
    @staticmethod
    def get_invite_by_code(invite_code: str) -> Optional[Invite]:
        """
        Find invite by its code.
        
        Args:
            invite_code: 8-character invite code
            
        Returns:
            Invite object or None
        """
        # Search through users' behavioral_flags for the code
        for user in User.objects.all():
            if not isinstance(user.behavioral_flags, dict):
                continue
            
            invite_codes = user.behavioral_flags.get('invite_codes', {})
            if invite_code in invite_codes:
                invite_id = invite_codes[invite_code]
                try:
                    return Invite.objects.get(id=invite_id)
                except Invite.DoesNotExist:
                    pass
        
        return None
