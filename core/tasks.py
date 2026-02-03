"""
Celery tasks for async operations.

Handles SMS sending, notifications, MRP expiration checks, and background processing.
"""

import os
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


@shared_task(bind=True, max_retries=3)
def send_verification_sms(self, phone_number: str, code: str):
    """
    Send SMS verification code via Twilio.
    
    Args:
        phone_number: Phone number to send to (E.164 format)
        code: 6-digit verification code
    """
    # Check if in test mode (use environment variable)
    if os.environ.get('TWILIO_TEST_MODE', 'true').lower() == 'true':
        # Mock mode - log instead of sending
        print(f"[MOCK SMS] To: {phone_number}, Code: {code}")
        return f"Mock SMS sent to {phone_number}"
    
    try:
        from twilio.rest import Client
        
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        from_number = os.environ.get('TWILIO_PHONE_NUMBER')
        
        if not all([account_sid, auth_token, from_number]):
            raise ValueError("Twilio credentials not configured")
        
        client = Client(account_sid, auth_token)
        
        message = client.messages.create(
            body=f"Your verification code is: {code}",
            from_=from_number,
            to=phone_number
        )
        
        return message.sid
    
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_invite_notification(invite_id: str):
    """
    Send notification about new discussion invite.
    
    Args:
        invite_id: UUID of the invite
    """
    from core.models import Invite
    
    try:
        invite = Invite.objects.get(id=invite_id)
        
        # In production, this would send push notification or email
        # For now, just log
        print(f"[NOTIFICATION] Discussion invite sent to {invite.invitee.username} "
              f"for {invite.discussion.topic_headline}")
        
        return f"Notification sent for invite {invite_id}"
    
    except Invite.DoesNotExist:
        return f"Invite {invite_id} not found"


@shared_task
def send_join_request_notification(request_id: str):
    """
    Notify approver of new join request.
    
    Args:
        request_id: UUID of the join request
    """
    from core.models import JoinRequest
    
    try:
        request = JoinRequest.objects.get(id=request_id)
        
        print(f"[NOTIFICATION] Join request from {request.requester.username} "
              f"for {request.discussion.topic_headline} sent to {request.approver.username}")
        
        return f"Notification sent for join request {request_id}"
    
    except JoinRequest.DoesNotExist:
        return f"Join request {request_id} not found"


@shared_task
def send_join_request_approved_notification(request_id: str):
    """
    Notify requester that join request was approved.
    
    Args:
        request_id: UUID of the join request
    """
    from core.models import JoinRequest
    
    try:
        request = JoinRequest.objects.get(id=request_id)
        
        print(f"[NOTIFICATION] Join request approved: {request.requester.username} "
              f"can now participate in {request.discussion.topic_headline}")
        
        return f"Approval notification sent for join request {request_id}"
    
    except JoinRequest.DoesNotExist:
        return f"Join request {request_id} not found"


@shared_task
def send_join_request_declined_notification(request_id: str):
    """
    Notify requester that join request was declined.
    
    Args:
        request_id: UUID of the join request
    """
    from core.models import JoinRequest
    
    try:
        request = JoinRequest.objects.get(id=request_id)
        
        print(f"[NOTIFICATION] Join request declined: {request.requester.username} "
              f"for {request.discussion.topic_headline}")
        
        return f"Decline notification sent for join request {request_id}"
    
    except JoinRequest.DoesNotExist:
        return f"Join request {request_id} not found"


@shared_task
def cleanup_expired_invites():
    """
    Periodic task to expire old invites.
    
    Runs daily to mark sent invites older than 30 days as expired.
    """
    from datetime import timedelta
    from core.models import Invite
    
    cutoff = timezone.now() - timedelta(days=30)
    
    expired_count = Invite.objects.filter(
        status='sent',
        sent_at__lt=cutoff
    ).update(status='expired')
    
    print(f"[CLEANUP] Marked {expired_count} invites as expired")
    
    return f"Expired {expired_count} invites"


@shared_task
def cleanup_expired_verification_codes():
    """
    Periodic task to clean up expired verification codes from cache.
    
    This is mostly handled by Redis TTL, but this ensures cleanup.
    """
    # Cache entries auto-expire, but we can log this for monitoring
    print("[CLEANUP] Verification code cleanup complete")
    return "Cleanup complete"


# Discussion and Round Management Tasks

@shared_task
def check_mrp_expirations():
    """
    Periodic task to check MRP expirations.
    
    Runs every minute to check all in-progress rounds for MRP expiration.
    """
    from core.models import Round, PlatformConfig
    from core.services.round_service import RoundService
    
    # Get all in-progress rounds
    in_progress_rounds = Round.objects.filter(status='in_progress')
    
    config = PlatformConfig.load()
    expired_count = 0
    
    for round in in_progress_rounds:
        # Check if in Phase 2 (has MRP)
        if RoundService.is_phase_1(round, config):
            continue
        
        # Check if MRP expired
        if RoundService.is_mrp_expired(round):
            print(f"[MRP] Round {round.id} (Discussion {round.discussion.id}) MRP expired")
            
            # Handle expiration
            RoundService.handle_mrp_expiration(round)
            expired_count += 1
            
            # Notify via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer:
                # Get non-responders
                responders = set(round.responses.values_list('user_id', flat=True))
                all_participants = round.discussion.participants.filter(
                    role__in=['initiator', 'active']
                ).values_list('user_id', flat=True)
                observers_added = [uid for uid in all_participants if uid not in responders]
                
                async_to_sync(channel_layer.group_send)(
                    f'discussion_{round.discussion.id}',
                    {
                        'type': 'mrp_expired',
                        'round_number': round.round_number,
                        'observers_added': observers_added
                    }
                )
    
    return f"Checked rounds, {expired_count} MRP expirations handled"


@shared_task
def check_phase_1_timeouts():
    """
    Periodic task to check Phase 1 timeouts.
    
    Runs daily to check if Round 1 Phase 1 discussions have timed out (30 days default).
    """
    from core.models import Round, PlatformConfig
    from core.services.round_service import RoundService
    
    config = PlatformConfig.load()
    
    # Get all Round 1, in-progress rounds
    round_1_rounds = Round.objects.filter(
        round_number=1,
        status='in_progress'
    )
    
    archived_count = 0
    
    for round in round_1_rounds:
        if RoundService.check_phase_1_timeout(round, config):
            print(f"[TIMEOUT] Discussion {round.discussion.id} archived due to Phase 1 timeout")
            archived_count += 1
            
            # Notify via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'discussion_{round.discussion.id}',
                    {
                        'type': 'discussion_archived',
                        'reason': 'phase_1_timeout'
                    }
                )
    
    return f"Checked Phase 1 timeouts, {archived_count} discussions archived"


@shared_task
def send_mrp_warning(discussion_id: int, round_number: int, percentage_remaining: int):
    """
    Send MRP expiration warning via WebSocket.
    
    Called when MRP is at 25%, 10%, or 5% remaining.
    
    Args:
        discussion_id: Discussion ID
        round_number: Round number
        percentage_remaining: Percentage of MRP time remaining
    """
    from core.models import Round
    from core.services.round_service import RoundService
    
    try:
        round_obj = Round.objects.get(
            discussion_id=discussion_id,
            round_number=round_number
        )
        
        mrp_deadline = RoundService.get_mrp_deadline(round_obj)
        
        if mrp_deadline:
            time_remaining = (mrp_deadline - timezone.now()).total_seconds() / 60  # minutes
            
            # Send WebSocket notification
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'discussion_{discussion_id}',
                    {
                        'type': 'mrp_warning',
                        'round_number': round_number,
                        'percentage_remaining': percentage_remaining,
                        'time_remaining_minutes': time_remaining,
                        'mrp_deadline': mrp_deadline.isoformat()
                    }
                )
            
            print(f"[MRP WARNING] Discussion {discussion_id} Round {round_number}: "
                  f"{percentage_remaining}% remaining")
        
        return f"Warning sent for discussion {discussion_id}"
        
    except Round.DoesNotExist:
        return f"Round not found: discussion {discussion_id}, round {round_number}"


@shared_task
def send_single_response_warning(discussion_id: int, round_number: int):
    """
    Send warning when round has only 1 response (will be archived if MRP expires).
    
    Args:
        discussion_id: Discussion ID
        round_number: Round number
    """
    from core.models import Round
    
    try:
        round_obj = Round.objects.get(
            discussion_id=discussion_id,
            round_number=round_number
        )
        
        response_count = round_obj.responses.count()
        
        if response_count <= 1:
            print(f"[WARNING] Discussion {discussion_id} Round {round_number} has only "
                  f"{response_count} response(s) - will be archived if MRP expires")
            
            # Could send notification to participants here
        
        return f"Single response warning for discussion {discussion_id}"
        
    except Round.DoesNotExist:
        return f"Round not found: discussion {discussion_id}, round {round_number}"


@shared_task
def broadcast_new_response(discussion_id: int, response_id: int):
    """
    Broadcast new response via WebSocket.
    
    Args:
        discussion_id: Discussion ID
        response_id: Response ID
    """
    from core.models import Response
    from core.services.response_service import ResponseService
    from core.services.round_service import RoundService
    
    try:
        response = Response.objects.get(id=response_id)
        round_obj = response.round
        
        # Get response number
        response_number = ResponseService.get_response_number(response)
        
        # Get MRP info
        mrp_deadline = RoundService.get_mrp_deadline(round_obj)
        
        # Send WebSocket notification
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'discussion_{discussion_id}',
                {
                    'type': 'new_response',
                    'response_id': str(response.id),
                    'author': response.user.username,
                    'round_number': round_obj.round_number,
                    'response_number': response_number,
                    'mrp_updated': True,
                    'new_mrp_minutes': round_obj.final_mrp_minutes,
                    'new_mrp_deadline': mrp_deadline.isoformat() if mrp_deadline else None
                }
            )
        
        return f"Broadcast response {response_id} for discussion {discussion_id}"
        
    except Response.DoesNotExist:
        return f"Response {response_id} not found"


@shared_task
def close_voting_windows():
    """
    Periodic task (every minute):
    - Find rounds with status='voting' where window expired
    - Call VotingService.close_voting_window
    - Call ModerationVotingService.resolve_removal_votes
    - Create next round or archive discussion
    """
    from core.models import Round, PlatformConfig
    from core.services.voting_service import VotingService
    from core.services.moderation_voting_service import ModerationVotingService
    from core.services.multi_round_service import MultiRoundService
    from datetime import timedelta
    
    config = PlatformConfig.load()
    now = timezone.now()
    
    # Find voting rounds where window has expired
    voting_rounds = Round.objects.filter(status='voting')
    
    closed_count = 0
    for round_obj in voting_rounds:
        if round_obj.end_time and round_obj.final_mrp_minutes:
            window_close_time = round_obj.end_time + timedelta(minutes=round_obj.final_mrp_minutes)
            
            if now >= window_close_time:
                # Close voting window
                VotingService.close_voting_window(round_obj, config)
                
                # Resolve removal votes
                removed_users = ModerationVotingService.resolve_removal_votes(round_obj, config)
                
                # Send notifications for removed users
                for user in removed_users:
                    send_permanent_observer_notification.delay(
                        user.id,
                        round_obj.discussion.id,
                        "vote_based_removal"
                    )
                
                # Create next round or archive
                next_round = MultiRoundService.create_next_round(
                    round_obj.discussion,
                    round_obj
                )
                
                # Broadcast events
                channel_layer = get_channel_layer()
                if channel_layer:
                    if next_round:
                        async_to_sync(channel_layer.group_send)(
                            f'discussion_{round_obj.discussion.id}',
                            {
                                'type': 'next_round_started',
                                'round_number': next_round.round_number,
                                'discussion_id': round_obj.discussion.id
                            }
                        )
                    elif round_obj.discussion.status == 'archived':
                        async_to_sync(channel_layer.group_send)(
                            f'discussion_{round_obj.discussion.id}',
                            {
                                'type': 'discussion_archived',
                                'discussion_id': round_obj.discussion.id,
                                'reason': 'Termination condition met'
                            }
                        )
                
                closed_count += 1
    
    return f"Closed {closed_count} voting windows"


@shared_task
def check_discussion_termination():
    """
    Periodic task (hourly):
    - Check all active discussions for termination conditions
    - Archive if conditions met
    """
    from core.models import Discussion, Round, PlatformConfig
    from core.services.multi_round_service import MultiRoundService
    
    config = PlatformConfig.load()
    active_discussions = Discussion.objects.filter(status='active')
    
    archived_count = 0
    for discussion in active_discussions:
        # Get latest round
        latest_round = discussion.rounds.order_by('-round_number').first()
        
        if latest_round:
            should_archive, reason = MultiRoundService.check_termination_conditions(
                discussion, latest_round, config
            )
            
            if should_archive:
                MultiRoundService.archive_discussion(discussion, reason)
                
                # Broadcast event
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f'discussion_{discussion.id}',
                        {
                            'type': 'discussion_archived',
                            'discussion_id': discussion.id,
                            'reason': reason
                        }
                    )
                
                archived_count += 1
    
    return f"Archived {archived_count} discussions"


@shared_task
def send_voting_window_closing_warning(round_id: int, time_remaining: int):
    """
    Send warning when voting window closing soon.
    
    Args:
        round_id: Round ID
        time_remaining: Minutes remaining
    """
    from core.models import Round
    
    try:
        round_obj = Round.objects.get(id=round_id)
        # In production, send actual notifications
        print(f"[WARNING] Voting window for Round {round_obj.round_number} closing in {time_remaining} minutes")
        return f"Sent warning for round {round_id}"
    except Round.DoesNotExist:
        return f"Round {round_id} not found"


@shared_task
def send_removal_warning(user_id: int, discussion_id: int, votes_against: int, threshold: float):
    """
    Warn user they may be removed.
    
    Args:
        user_id: User ID
        discussion_id: Discussion ID
        votes_against: Number of votes against user
        threshold: Threshold percentage
    """
    from core.models import User, Discussion
    
    try:
        user = User.objects.get(id=user_id)
        discussion = Discussion.objects.get(id=discussion_id)
        print(f"[WARNING] User {user.username} has {votes_against} votes against them (threshold: {threshold}%)")
        return f"Sent removal warning to user {user_id}"
    except (User.DoesNotExist, Discussion.DoesNotExist):
        return "User or discussion not found"


@shared_task
def send_permanent_observer_notification(user_id: int, discussion_id: int, consequence: str):
    """
    Notify user of permanent observer consequences.
    
    Args:
        user_id: User ID
        discussion_id: Discussion ID
        consequence: Type of consequence
    """
    from core.models import User, Discussion
    
    try:
        user = User.objects.get(id=user_id)
        discussion = Discussion.objects.get(id=discussion_id)
        print(f"[NOTIFICATION] User {user.username} became permanent observer due to: {consequence}")
        return f"Sent permanent observer notification to user {user_id}"
    except (User.DoesNotExist, Discussion.DoesNotExist):
        return "User or discussion not found"


    print("[CLEANUP] Verification code cleanup completed")
    return "Verification code cleanup completed"

