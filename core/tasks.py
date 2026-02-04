"""
Celery tasks for async operations.

Handles SMS sending, notifications, MRP expiration checks, and background processing.
"""

import os
import logging
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_verification_sms(self, phone_number: str, code: str):
    """
    Send SMS verification code via Twilio.

    Args:
        phone_number: Phone number to send to (E.164 format)
        code: 6-digit verification code
    """
    # Check if in test mode (use environment variable)
    if os.environ.get("TWILIO_TEST_MODE", "true").lower() == "true":
        # Mock mode - log instead of sending
        # SECURITY: Never log verification codes or full phone numbers
        masked_phone = f"***-***-{phone_number[-4:]}" if len(phone_number) >= 4 else "***-***-****"
        logger.info(f"[MOCK SMS] Verification code sent to {masked_phone}")
        return f"Mock SMS sent to {masked_phone}"

    try:
        from twilio.rest import Client

        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        from_number = os.environ.get("TWILIO_PHONE_NUMBER")

        if not all([account_sid, auth_token, from_number]):
            raise ValueError("Twilio credentials not configured")

        client = Client(account_sid, auth_token)

        message = client.messages.create(
            body=f"Your verification code is: {code}",
            from_=from_number,
            to=phone_number,
        )

        return message.sid

    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


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
        logger.info(
            f"Discussion invite sent to {invite.invitee.username} "
            f"for discussion: {invite.discussion.topic_headline}"
        )

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

        logger.info(
            f"Join request from {request.requester.username} "
            f"for {request.discussion.topic_headline} sent to {request.approver.username}"
        )

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

        logger.info(
            f"Join request approved: {request.requester.username} "
            f"can now participate in {request.discussion.topic_headline}"
        )

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

        logger.info(
            f"Join request declined: {request.requester.username} "
            f"for {request.discussion.topic_headline}"
        )

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

    expired_count = Invite.objects.filter(status="sent", sent_at__lt=cutoff).update(
        status="expired"
    )

    logger.info(f"Marked {expired_count} invites as expired")

    return f"Expired {expired_count} invites"


@shared_task
def cleanup_expired_verification_codes():
    """
    Periodic task to clean up expired verification codes from cache.

    This is mostly handled by Redis TTL, but this ensures cleanup.
    """
    # Cache entries auto-expire, but we can log this for monitoring
    logger.debug("Verification code cleanup complete")
    return "Cleanup complete"


# Discussion and Round Management Tasks


@shared_task
def broadcast_mrp_timers():
    """
    Broadcast MRP timer updates every 60 seconds for all active rounds.
    
    This task should run every minute via Celery Beat to provide real-time
    countdown updates to all connected WebSocket clients.
    """
    from core.models import Round, Discussion
    
    # Get all active rounds with MRP deadlines
    active_rounds = Round.objects.filter(
        discussion__status='active',
        status='in_progress',
        mrp_deadline__isnull=False
    ).select_related('discussion')
    
    channel_layer = get_channel_layer()
    if not channel_layer:
        return "Channel layer not configured"
    
    broadcast_count = 0
    for round_obj in active_rounds:
        time_remaining = (round_obj.mrp_deadline - timezone.now()).total_seconds()
        if time_remaining > 0:
            async_to_sync(channel_layer.group_send)(
                f"discussion_{round_obj.discussion.id}",
                {
                    "type": "mrp_timer_update",
                    "round_number": round_obj.round_number,
                    "time_remaining_seconds": int(time_remaining),
                    "mrp_deadline": round_obj.mrp_deadline.isoformat(),
                }
            )
            broadcast_count += 1
    
    return f"Broadcasted MRP timers for {broadcast_count} rounds"


@shared_task
def check_mrp_expirations():
    """
    Periodic task to check MRP expirations.

    Runs every minute to check all in-progress rounds for MRP expiration.
    """
    from core.models import Round, PlatformConfig
    from core.services.round_service import RoundService

    # Get all in-progress rounds
    in_progress_rounds = Round.objects.filter(status="in_progress")

    config = PlatformConfig.load()
    expired_count = 0

    for round in in_progress_rounds:
        # Check if in Phase 2 (has MRP)
        if RoundService.is_phase_1(round, config):
            continue

        # Check if MRP expired
        if RoundService.is_mrp_expired(round):
            logger.info(
                f"MRP expired for Round {round.id} in Discussion {round.discussion.id}"
            )

            # Handle expiration
            RoundService.handle_mrp_expiration(round)
            expired_count += 1

            # Notify via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer:
                # Get non-responders
                responders = set(round.responses.values_list("user_id", flat=True))
                all_participants = round.discussion.participants.filter(
                    role__in=["initiator", "active"]
                ).values_list("user_id", flat=True)
                observers_added = [
                    uid for uid in all_participants if uid not in responders
                ]

                async_to_sync(channel_layer.group_send)(
                    f"discussion_{round.discussion.id}",
                    {
                        "type": "mrp_expired",
                        "round_number": round.round_number,
                        "observers_added": observers_added,
                    },
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
    round_1_rounds = Round.objects.filter(round_number=1, status="in_progress")

    archived_count = 0

    for round in round_1_rounds:
        if RoundService.check_phase_1_timeout(round, config):
            logger.info(
                f"Discussion {round.discussion.id} archived due to Phase 1 timeout"
            )
            archived_count += 1

            # Notify via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"discussion_{round.discussion.id}",
                    {"type": "discussion_archived", "reason": "phase_1_timeout"},
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
            discussion_id=discussion_id, round_number=round_number
        )

        mrp_deadline = RoundService.get_mrp_deadline(round_obj)

        if mrp_deadline:
            time_remaining = (
                mrp_deadline - timezone.now()
            ).total_seconds() / 60  # minutes

            # Send WebSocket notification
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"discussion_{discussion_id}",
                    {
                        "type": "mrp_warning",
                        "round_number": round_number,
                        "percentage_remaining": percentage_remaining,
                        "time_remaining_minutes": time_remaining,
                        "mrp_deadline": mrp_deadline.isoformat(),
                    },
                )

            logger.info(
                f"MRP warning sent for Discussion {discussion_id} Round {round_number}: "
                f"{percentage_remaining}% remaining"
            )

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
            discussion_id=discussion_id, round_number=round_number
        )

        response_count = round_obj.responses.count()

        if response_count <= 1:
            logger.warning(
                f"Discussion {discussion_id} Round {round_number} has only "
                f"{response_count} response(s) - will be archived if MRP expires"
            )

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
                f"discussion_{discussion_id}",
                {
                    "type": "new_response",
                    "response_id": str(response.id),
                    "author": response.user.username,
                    "round_number": round_obj.round_number,
                    "response_number": response_number,
                    "mrp_updated": True,
                    "new_mrp_minutes": round_obj.final_mrp_minutes,
                    "new_mrp_deadline": (
                        mrp_deadline.isoformat() if mrp_deadline else None
                    ),
                },
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
    voting_rounds = Round.objects.filter(status="voting")

    closed_count = 0
    for round_obj in voting_rounds:
        if round_obj.end_time and round_obj.final_mrp_minutes:
            window_close_time = round_obj.end_time + timedelta(
                minutes=round_obj.final_mrp_minutes
            )

            if now >= window_close_time:
                # Close voting window
                VotingService.close_voting_window(round_obj, config)

                # Resolve removal votes
                removed_users = ModerationVotingService.resolve_removal_votes(
                    round_obj, config
                )

                # Send notifications for removed users
                for user in removed_users:
                    send_permanent_observer_notification.delay(
                        user.id, round_obj.discussion.id, "vote_based_removal"
                    )

                # Create next round or archive
                next_round = MultiRoundService.create_next_round(
                    round_obj.discussion, round_obj
                )

                # Broadcast events
                channel_layer = get_channel_layer()
                if channel_layer:
                    if next_round:
                        async_to_sync(channel_layer.group_send)(
                            f"discussion_{round_obj.discussion.id}",
                            {
                                "type": "next_round_started",
                                "round_number": next_round.round_number,
                                "discussion_id": round_obj.discussion.id,
                            },
                        )
                    elif round_obj.discussion.status == "archived":
                        async_to_sync(channel_layer.group_send)(
                            f"discussion_{round_obj.discussion.id}",
                            {
                                "type": "discussion_archived",
                                "discussion_id": round_obj.discussion.id,
                                "reason": "Termination condition met",
                            },
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
    active_discussions = Discussion.objects.filter(status="active")

    archived_count = 0
    for discussion in active_discussions:
        # Get latest round
        latest_round = discussion.rounds.order_by("-round_number").first()

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
                        f"discussion_{discussion.id}",
                        {
                            "type": "discussion_archived",
                            "discussion_id": discussion.id,
                            "reason": reason,
                        },
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
        logger.info(
            f"Voting window for Round {round_obj.round_number} closing in {time_remaining} minutes"
        )
        return f"Sent warning for round {round_id}"
    except Round.DoesNotExist:
        return f"Round {round_id} not found"


@shared_task
def send_removal_warning(
    user_id: int, discussion_id: int, votes_against: int, threshold: float
):
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
        logger.warning(
            f"User {user.username} has {votes_against} votes against them (threshold: {threshold}%)"
        )
        return f"Sent removal warning to user {user_id}"
    except (User.DoesNotExist, Discussion.DoesNotExist):
        return "User or discussion not found"


@shared_task
def send_permanent_observer_notification(
    user_id: int, discussion_id: int, consequence: str
):
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
        logger.info(
            f"User {user.username} became permanent observer due to: {consequence}"
        )
        return f"Sent permanent observer notification to user {user_id}"
    except (User.DoesNotExist, Discussion.DoesNotExist):
        return "User or discussion not found"


@shared_task
def check_mrp_expirations():
    """
    Run every 5 minutes:
    - Find active participants with MRP expiring soon
    - Send warnings at 25%, 10%, 5% remaining
    - Track which warnings already sent to avoid duplicates
    """
    from core.models import Discussion, Round, Response
    from core.services.notification_service import NotificationService
    from core.services.response_service import ResponseService

    now = timezone.now()
    warnings_sent = 0

    # Find all active discussions with in-progress rounds
    active_rounds = Round.objects.filter(
        status="in_progress", discussion__status="active"
    ).select_related("discussion")

    for round_obj in active_rounds:
        # Get active participants who haven't responded yet
        participants = round_obj.discussion.participants.filter(
            role__in=["initiator", "active"]
        ).select_related("user")

        for participant in participants:
            # Check if user already responded in this round
            has_responded = Response.objects.filter(
                round=round_obj, author=participant.user
            ).exists()

            if has_responded:
                continue

            # Get time remaining for this user
            time_remaining = ResponseService.get_time_remaining(
                participant.user, round_obj.discussion, round_obj
            )

            if not time_remaining:
                continue

            # Calculate MRP deadline
            mrp_minutes = (
                round_obj.final_mrp_minutes
                or round_obj.discussion.min_response_time_minutes
            )
            total_seconds = mrp_minutes * 60
            remaining_seconds = time_remaining.total_seconds()

            if remaining_seconds <= 0:
                continue

            percentage_remaining = (remaining_seconds / total_seconds) * 100

            # Check thresholds: 25%, 10%, 5%
            warning_threshold = None
            if 4 <= percentage_remaining <= 6:
                warning_threshold = 5
            elif 9 <= percentage_remaining <= 11:
                warning_threshold = 10
            elif 24 <= percentage_remaining <= 26:
                warning_threshold = 25

            if warning_threshold:
                # Check if we already sent this warning (use cache)
                cache_key = f"mrp_warning_{participant.user.id}_{round_obj.id}_{warning_threshold}"
                if not cache.get(cache_key):
                    NotificationService.send_mrp_expiring_warning(
                        participant.user,
                        round_obj.discussion,
                        round_obj,
                        warning_threshold,
                    )
                    # Cache for 1 hour to prevent duplicate warnings
                    cache.set(cache_key, True, 3600)
                    warnings_sent += 1

    return f"Sent {warnings_sent} MRP expiration warnings"


@shared_task
def check_voting_windows():
    """
    Run every hour:
    - Find voting windows closing in next 24 hours
    - Send closing reminders
    - Find voting windows that just opened
    - Send opening notifications (if user opted in)
    """
    from core.models import Round
    from core.services.notification_service import NotificationService

    now = timezone.now()

    # Find voting rounds closing in next 24 hours
    closing_rounds = Round.objects.filter(
        status="voting", discussion__status="active"
    ).select_related("discussion")

    closing_sent = 0
    for round_obj in closing_rounds:
        if round_obj.end_time and round_obj.final_mrp_minutes:
            window_close_time = round_obj.end_time + timedelta(
                minutes=round_obj.final_mrp_minutes
            )
            time_until_close = window_close_time - now

            # Send reminder if closing in 20-24 hours
            if timedelta(hours=20) <= time_until_close <= timedelta(hours=24):
                cache_key = f"voting_closing_{round_obj.id}"
                if not cache.get(cache_key):
                    NotificationService.send_voting_notifications(
                        round_obj.discussion, round_obj, "closing"
                    )
                    cache.set(cache_key, True, 86400)  # 24 hours
                    closing_sent += 1

    # Find voting rounds that opened in last hour
    recently_opened = Round.objects.filter(
        status="voting",
        discussion__status="active",
        end_time__gte=now - timedelta(hours=1),
        end_time__lte=now,
    ).select_related("discussion")

    opening_sent = 0
    for round_obj in recently_opened:
        cache_key = f"voting_opened_{round_obj.id}"
        if not cache.get(cache_key):
            NotificationService.send_voting_notifications(
                round_obj.discussion, round_obj, "opened"
            )
            cache.set(cache_key, True, 86400)  # 24 hours
            opening_sent += 1

    return (
        f"Sent {closing_sent} closing warnings and {opening_sent} opening notifications"
    )


@shared_task
def check_discussion_archive_warnings():
    """
    Run every hour:
    - Find discussions in rounds with ≤1 response
    - Send archive warnings to participants
    """
    from core.models import Round, Response
    from core.services.notification_service import NotificationService

    # Find in-progress rounds
    active_rounds = Round.objects.filter(
        status="in_progress", discussion__status="active"
    ).select_related("discussion")

    warnings_sent = 0
    for round_obj in active_rounds:
        # Count responses in this round
        response_count = Response.objects.filter(round=round_obj).count()

        if response_count <= 1:
            # Check if warning already sent
            cache_key = f"archive_warning_{round_obj.discussion.id}_{round_obj.id}"
            if not cache.get(cache_key):
                NotificationService.send_discussion_archive_warning(
                    round_obj.discussion, round_obj
                )
                cache.set(cache_key, True, 86400)  # 24 hours
                warnings_sent += 1

    return f"Sent {warnings_sent} archive warnings"


@shared_task
def send_daily_digest():
    """
    Daily digest email (if user opted in):
    - Active discussions needing response
    - Pending invites
    - Voting windows closing
    """
    from core.models import User, Discussion, Invite, Round, Response
    from django.core.mail import send_mail

    users = User.objects.filter(is_active=True)

    digests_sent = 0
    for user in users:
        # Check if user opted in to daily digest
        # For now, skip this feature (TODO: implement opt-in)
        pass

    return f"Sent {digests_sent} daily digests"


@shared_task
def run_abuse_detection():
    """
    Run abuse detection on recent user activity.

    Runs every hour:
    - Scan recent user activity
    - Run abuse detection algorithms
    - Auto-moderate high-confidence cases
    - Flag medium-confidence cases for admin review
    - Send notifications to admins for new flags
    """
    from core.models import User
    from core.security.abuse_detection import AbuseDetectionService
    from django.utils import timezone
    from datetime import timedelta

    # Get users active in last 24 hours
    cutoff = timezone.now() - timedelta(hours=24)
    active_users = User.objects.filter(last_login__gte=cutoff)

    actions_taken = {"auto_ban": 0, "flagged_for_review": 0, "monitored": 0}

    for user in active_users:
        # Skip already banned users
        if user.is_banned():
            continue

        # Run auto-moderation
        result = AbuseDetectionService.auto_moderate(user)
        action = result.get("action_taken")

        if action in actions_taken:
            actions_taken[action] += 1

    return f"Abuse detection completed: {actions_taken}"


@shared_task
def calculate_platform_health():
    """
    Daily platform health check.

    Daily:
    - Calculate engagement metrics
    - Detect anomalies (sudden drop in activity)
    - Identify trending issues
    - Alert admins if health score drops
    """
    from core.services.admin_service import AdminService
    from core.services.notification_service import NotificationService
    from core.models import User
    from django.core.cache import cache

    # Get current analytics
    analytics = AdminService.get_platform_analytics()

    # Get previous day's analytics from cache
    previous_analytics = cache.get("platform_health_previous")

    # Calculate health score (0-100)
    health_score = 100
    alerts = []

    if previous_analytics:
        # Check for significant drops
        current_active_7d = analytics["users"]["active_7_days"]
        previous_active_7d = previous_analytics["users"].get(
            "active_7_days", current_active_7d
        )

        if previous_active_7d > 0:
            activity_change = (
                current_active_7d - previous_active_7d
            ) / previous_active_7d

            if activity_change < -0.2:  # 20% drop
                health_score -= 20
                alerts.append(
                    f"Active users dropped by {abs(activity_change)*100:.1f}%"
                )

        # Check response rate
        current_responses = analytics["engagement"]["total_responses"]
        previous_responses = previous_analytics["engagement"].get(
            "total_responses", current_responses
        )

        if previous_responses > 0:
            response_change = (
                current_responses - previous_responses
            ) / previous_responses

            if response_change < -0.3:  # 30% drop
                health_score -= 15
                alerts.append(
                    f"Response rate dropped by {abs(response_change)*100:.1f}%"
                )

    # Check abuse metrics
    if analytics["abuse"]["auto_bans"] > 5:
        health_score -= 10
        alerts.append(f'High number of auto-bans: {analytics["abuse"]["auto_bans"]}')

    # Store current analytics for next comparison
    cache.set("platform_health_previous", analytics, 86400 * 7)  # 7 days

    # Alert admins if health score is low
    if health_score < 70:
        admin_users = User.objects.filter(is_staff=True)
        for admin in admin_users:
            NotificationService.send_notification(
                user=admin,
                notification_type="platform_health_alert",
                title="Platform Health Alert",
                message=f"Platform health score: {health_score}/100",
                context={
                    "health_score": health_score,
                    "alerts": alerts,
                    "analytics": analytics,
                },
            )

    return f"Platform health score: {health_score}/100. Alerts: {len(alerts)}"


@shared_task
def cleanup_old_data():
    """
    Weekly cleanup of old data.

    Weekly:
    - Expired verification codes (>24 hours)
    - Old notifications (>90 days)
    - Expired invites (>30 days)
    - Resolved flags (>365 days)
    - Log cleanup statistics
    """
    from core.models import Invite, NotificationLog, AdminFlag
    from django.utils import timezone
    from datetime import timedelta
    from django.core.cache import cache

    now = timezone.now()

    # Clean up verification codes from cache
    # Note: Cache entries expire automatically, but we can clean patterns
    verification_codes_cleaned = 0

    # Clean up old notifications (>90 days)
    notification_cutoff = now - timedelta(days=90)
    notifications_deleted = NotificationLog.objects.filter(
        created_at__lt=notification_cutoff, read=True
    ).delete()[0]

    # Clean up expired invites (>30 days and pending)
    invite_cutoff = now - timedelta(days=30)
    invites_deleted = Invite.objects.filter(
        sent_at__lt=invite_cutoff, status="pending"
    ).delete()[0]

    # Clean up resolved flags (>365 days)
    flag_cutoff = now - timedelta(days=365)
    flags_deleted = AdminFlag.objects.filter(
        resolved_at__lt=flag_cutoff, status="resolved"
    ).delete()[0]

    # Log cleanup statistics
    from core.services.audit_service import AuditService
    from core.models import User

    # Use first admin or create system user
    admin = User.objects.filter(is_staff=True).first()
    if admin:
        AuditService.log_admin_action(
            admin=admin,
            action_type="cleanup_old_data",
            target_type="system",
            target_id="cleanup",
            details={
                "notifications_deleted": notifications_deleted,
                "invites_deleted": invites_deleted,
                "flags_deleted": flags_deleted,
            },
            reason="Automated weekly cleanup",
        )

    return f"Cleanup: {notifications_deleted} notifications, {invites_deleted} invites, {flags_deleted} flags"


@shared_task
def auto_archive_abandoned_discussions():
    """
    Weekly task to auto-archive abandoned discussions.

    Weekly:
    - Find discussions with no activity for 60+ days
    - Auto-archive with reason 'abandoned'
    - Send notifications to participants
    """
    from core.models import Discussion, Round, Response
    from core.services.notification_service import NotificationService
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()
    abandoned_cutoff = now - timedelta(days=60)

    # Find active discussions
    active_discussions = Discussion.objects.filter(status="active")

    archived_count = 0

    for discussion in active_discussions:
        # Get last activity
        last_response = (
            Response.objects.filter(round__discussion=discussion)
            .order_by("-created_at")
            .first()
        )

        if last_response:
            last_activity = last_response.created_at
        else:
            last_activity = discussion.created_at

        # Check if abandoned
        if last_activity < abandoned_cutoff:
            # Archive discussion
            discussion.status = "archived"
            discussion.archived_at = now
            discussion.save()

            archived_count += 1

            # Notify participants
            participants = discussion.participants.all()
            for participant in participants:
                NotificationService.send_notification(
                    user=participant.user,
                    notification_type="discussion_auto_archived",
                    title="Discussion Archived (Abandoned)",
                    message=f'Discussion "{discussion.topic_headline}" has been archived due to inactivity',
                    context={
                        "discussion_id": discussion.id,
                        "reason": "abandoned",
                        "last_activity": last_activity.isoformat(),
                    },
                )

    return f"Auto-archived {archived_count} abandoned discussions"


@shared_task
def generate_admin_reports():
    """
    Weekly admin reports.

    Weekly:
    - Platform health summary
    - Top abuse patterns
    - User growth trends
    - Engagement metrics
    - Send to admin team
    """
    from core.services.admin_service import AdminService
    from core.security.abuse_detection import AbuseDetectionService
    from core.services.notification_service import NotificationService
    from core.models import User
    from django.utils import timezone
    from datetime import timedelta

    # Get analytics
    analytics = AdminService.get_platform_analytics()

    # Get abuse patterns
    abuse_patterns = AbuseDetectionService.get_abuse_patterns()

    # Calculate week-over-week growth
    # (Would need historical data - simplified for now)

    # Build report
    report = {
        "period": "Weekly Report",
        "generated_at": timezone.now().isoformat(),
        "analytics": analytics,
        "abuse_patterns": abuse_patterns,
        "highlights": [
            f"Total users: {analytics['users']['total']}",
            f"Active (7d): {analytics['users']['active_7_days']}",
            f"New this week: {analytics['users']['new_this_week']}",
            f"Active discussions: {analytics['discussions']['active']}",
            f"Flags pending: {analytics['moderation']['active_flags']}",
        ],
    }

    # Send to all admins
    admin_users = User.objects.filter(is_staff=True)
    for admin in admin_users:
        NotificationService.send_notification(
            user=admin,
            notification_type="weekly_admin_report",
            title="Weekly Admin Report",
            message=f'Platform report for week ending {timezone.now().strftime("%Y-%m-%d")}',
            context=report,
        )

    return f"Generated and sent weekly report to {admin_users.count()} admins"
