"""
Join request service for discussion participation requests.

Handles observer requests to join active discussions.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import User, Discussion, JoinRequest, DiscussionParticipant, PlatformConfig


class JoinRequestService:
    """
    Handle observer requests to join discussions.
    """
    
    @staticmethod
    def create_request(
        discussion: Discussion,
        requester: User,
        message: str = ""
    ) -> JoinRequest:
        """
        Observer requests to join discussion.
        
        Args:
            discussion: Discussion to join
            requester: User requesting to join
            message: Optional message to initiator
            
        Returns:
            Created JoinRequest object
            
        Raises:
            ValidationError: If request cannot be created
        """
        # Validate discussion not archived
        if discussion.status == 'archived':
            raise ValidationError("Cannot request to join archived discussions")
        
        # Validate requester is not already a participant
        if DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=requester
        ).exists():
            raise ValidationError("You are already a participant in this discussion")
        
        # Check if discussion is at cap
        config = PlatformConfig.objects.get(pk=1)
        current_participants = DiscussionParticipant.objects.filter(
            discussion=discussion,
            role='active'
        ).count()
        
        if current_participants >= config.max_discussion_participants:
            raise ValidationError("Discussion is at maximum capacity")
        
        # Check if pending request exists
        if JoinRequest.objects.filter(
            discussion=discussion,
            requester=requester,
            status='pending'
        ).exists():
            raise ValidationError("You already have a pending request for this discussion")
        
        # Get discussion initiator (approver)
        initiator_participant = DiscussionParticipant.objects.filter(
            discussion=discussion,
            role='active'
        ).order_by('joined_at').first()
        
        if not initiator_participant:
            raise ValidationError("Discussion has no active participants")
        
        # Create request
        join_request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=initiator_participant.user,
            request_message=message,
            status='pending'
        )
        
        # Send notification to approver
        from core.tasks import send_join_request_notification
        send_join_request_notification.delay(str(join_request.id))
        
        return join_request
    
    @staticmethod
    def approve_request(request: JoinRequest, approver: User) -> DiscussionParticipant:
        """
        Approve join request.
        
        Args:
            request: JoinRequest to approve
            approver: User approving the request
            
        Returns:
            Created DiscussionParticipant object
            
        Raises:
            ValidationError: If request cannot be approved
        """
        # Validate request is pending
        if request.status != 'pending':
            raise ValidationError("Request has already been processed")
        
        # Validate approver has authority
        if request.approver.id != approver.id:
            # Check if approver is discussion initiator or active participant
            is_participant = DiscussionParticipant.objects.filter(
                discussion=request.discussion,
                user=approver,
                role='active'
            ).exists()
            
            if not is_participant:
                raise ValidationError("You do not have permission to approve this request")
        
        # Check if discussion still has space
        config = PlatformConfig.objects.get(pk=1)
        current_participants = DiscussionParticipant.objects.filter(
            discussion=request.discussion,
            role='active'
        ).count()
        
        if current_participants >= config.max_discussion_participants:
            raise ValidationError("Discussion is now at maximum capacity")
        
        with transaction.atomic():
            # Add requester to discussion participants
            participant = DiscussionParticipant.objects.create(
                discussion=request.discussion,
                user=request.requester,
                role='active'
            )
            
            # Update request status
            request.status = 'approved'
            request.resolved_at = timezone.now()
            request.save()
            
            # Send notification to requester
            from core.tasks import send_join_request_approved_notification
            send_join_request_approved_notification.delay(str(request.id))
        
        return participant
    
    @staticmethod
    def decline_request(
        request: JoinRequest,
        approver: User,
        message: str = ""
    ) -> None:
        """
        Decline join request.
        
        Args:
            request: JoinRequest to decline
            approver: User declining the request
            message: Optional message to requester
            
        Raises:
            ValidationError: If request cannot be declined
        """
        # Validate request is pending
        if request.status != 'pending':
            raise ValidationError("Request has already been processed")
        
        # Validate approver has authority
        if request.approver.id != approver.id:
            is_participant = DiscussionParticipant.objects.filter(
                discussion=request.discussion,
                user=approver,
                role='active'
            ).exists()
            
            if not is_participant:
                raise ValidationError("You do not have permission to decline this request")
        
        # Update request status
        request.status = 'declined'
        request.response_message = message
        request.resolved_at = timezone.now()
        request.save()
        
        # Send notification to requester
        from core.tasks import send_join_request_declined_notification
        send_join_request_declined_notification.delay(str(request.id))
