"""
Comprehensive notification service.

Manages critical and optional notifications across multiple delivery methods
(in-app, email, push).
"""

from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import logging

from core.models import (
    User,
    Discussion,
    Round,
    NotificationPreference,
    NotificationLog,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Comprehensive notification system"""

    # Critical notifications (opt-out blocked, default ON)
    CRITICAL_NOTIFICATIONS = [
        "mrp_expiring_soon",  # 25%, 10%, 5% remaining
        "moved_to_observer",
        "discussion_will_archive",  # ≤1 response warning
        "permanent_observer_warning",  # before vote-based removal
        "voting_window_closing",
        "mutual_removal_initiated",
        "mutual_removal_escalation_warning",  # approaching 3 removals
        "account_banned",
        "account_unbanned",
        "platform_health_alert",
        "user_flagged",
        "user_banned",
        "auto_ban",
        "auto_flag",
    ]

    # Optional notifications (opt-in, default OFF)
    OPTIONAL_NOTIFICATIONS = [
        "your_turn_reminder",  # gentle reminder to respond
        "voting_window_opened",
        "discussion_archived",
        "discussion_auto_archived",
        "new_invite_received",
        "new_response_posted",
        "discussion_invite_accepted",
        "join_request_received",
        "join_request_resolved",
        "phone_verified",
        "flag_resolved",
        "weekly_admin_report",
        "config_updated",
    ]

    ALL_NOTIFICATION_TYPES = CRITICAL_NOTIFICATIONS + OPTIONAL_NOTIFICATIONS

    @staticmethod
    @transaction.atomic
    def send_notification(
        user: User,
        notification_type: str,
        context: Dict[str, Any],
        delivery_methods: Optional[List[str]] = None,
        title: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        """
        Send notification to user.

        Args:
            user: User to notify
            notification_type: Type of notification
            context: Notification context data
            delivery_methods: List of ['in_app', 'email', 'push']. Defaults to ['in_app']
            title: Notification title (auto-generated if not provided)
            message: Notification message (auto-generated if not provided)
        """
        if delivery_methods is None:
            delivery_methods = ["in_app"]

        is_critical = notification_type in NotificationService.CRITICAL_NOTIFICATIONS

        # Get or create user's notification preferences
        try:
            preference = NotificationPreference.objects.get(
                user=user, notification_type=notification_type
            )
        except NotificationPreference.DoesNotExist:
            # Create default preference
            preference = NotificationPreference.objects.create(
                user=user,
                notification_type=notification_type,
                enabled=is_critical,  # Critical always enabled, optional disabled
                delivery_method={"in_app": True, "email": False, "push": False},
            )

        # Critical notifications always sent to in_app (cannot disable)
        if is_critical:
            if "in_app" not in delivery_methods:
                delivery_methods.append("in_app")
        else:
            # Optional notifications only sent if enabled
            if not preference.enabled:
                logger.info(
                    f"Notification {notification_type} disabled for user {user.username}"
                )
                return

        # Generate title and message if not provided
        if not title or not message:
            generated_title, generated_message = (
                NotificationService._generate_notification_content(
                    notification_type, context
                )
            )
            title = title or generated_title
            message = message or generated_message

        # Always store in NotificationLog for in_app
        if "in_app" in delivery_methods:
            notification_log = NotificationLog.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                message=message,
                context=context,
                is_critical=is_critical,
            )

            # Push to WebSocket if user is connected
            NotificationService._push_to_websocket(
                user,
                notification_log,
                notification_type,
                title,
                message,
                context,
                is_critical,
            )

        # Send email if requested and enabled
        if "email" in delivery_methods and preference.delivery_method.get(
            "email", False
        ):
            NotificationService._send_email(user, title, message, notification_type, context)

        # Send push if requested and enabled
        if "push" in delivery_methods and preference.delivery_method.get("push", False):
            NotificationService._send_push(user, title, message, context)

        logger.info(f"Notification sent to {user.username}: {notification_type}")

    @staticmethod
    def _generate_notification_content(
        notification_type: str, context: Dict[str, Any]
    ) -> tuple[str, str]:
        """
        Generate notification title and message based on type and context.

        Args:
            notification_type: Type of notification
            context: Notification context

        Returns:
            Tuple of (title, message)
        """
        templates = {
            "mrp_expiring_soon": (
                "Response time running out",
                f"You have {context.get('time_remaining', 'limited time')} remaining to respond in '{context.get('discussion_headline', 'discussion')}'",
            ),
            "moved_to_observer": (
                "Moved to observer status",
                f"You have been moved to {context.get('observer_type', 'observer')} status in '{context.get('discussion_headline', 'discussion')}'",
            ),
            "discussion_will_archive": (
                "Discussion will archive",
                f"'{context.get('discussion_headline', 'discussion')}' will archive if no more responses are received",
            ),
            "permanent_observer_warning": (
                "Permanent observer warning",
                f"You may become a permanent observer in '{context.get('discussion_headline', 'discussion')}' due to votes against you",
            ),
            "voting_window_closing": (
                "Voting window closing soon",
                f"Voting closes in {context.get('time_remaining', '24 hours')} for '{context.get('discussion_headline', 'discussion')}'",
            ),
            "mutual_removal_initiated": (
                "Mutual removal occurred",
                context.get("message", "A mutual removal has occurred"),
            ),
            "mutual_removal_escalation_warning": (
                "Approaching removal limit",
                f"You have initiated {context.get('removal_count', 0)} of 3 allowed removals. Reaching 3 will make you a permanent observer.",
            ),
            "your_turn_reminder": (
                "Your turn to respond",
                f"It's your turn to respond in '{context.get('discussion_headline', 'discussion')}'",
            ),
            "voting_window_opened": (
                "Voting has opened",
                f"Voting is now open for round {context.get('round_number', '')} in '{context.get('discussion_headline', 'discussion')}'",
            ),
            "discussion_archived": (
                "Discussion archived",
                f"'{context.get('discussion_headline', 'discussion')}' has been archived",
            ),
            "new_invite_received": (
                "New invitation",
                f"You've been invited to '{context.get('discussion_headline', 'discussion')}'",
            ),
            "new_response_posted": (
                "New response posted",
                f"New response in '{context.get('discussion_headline', 'discussion')}'",
            ),
            "discussion_invite_accepted": (
                "Invitation accepted",
                f"{context.get('user_name', 'A user')} accepted your invitation to '{context.get('discussion_headline', 'discussion')}'",
            ),
            "join_request_received": (
                "Join request received",
                f"{context.get('user_name', 'A user')} requested to join '{context.get('discussion_headline', 'discussion')}'",
            ),
            "join_request_resolved": (
                "Join request resolved",
                f"Your join request for '{context.get('discussion_headline', 'discussion')}' was {context.get('status', 'resolved')}",
            ),
        }

        return templates.get(
            notification_type, ("Notification", "You have a new notification")
        )

    @staticmethod
    def _send_email(user: User, title: str, message: str, notification_type: str = None, context: Dict = None) -> None:
        """
        Send email notification using templates.
        
        Args:
            user: User to send email to
            title: Email title
            message: Email message (fallback if no template)
            notification_type: Type of notification for template selection
            context: Additional context for template rendering
        """
        from core.services.email_service import EmailService
        
        try:
            # Use EmailService for templated emails when we have the type
            if notification_type and context:
                # Map notification types to email service methods
                template_map = {
                    'discussion_invite': 'send_discussion_invite',
                    'mrp_expiring': 'send_mrp_expiring_email',
                    'voting_started': 'send_voting_started_email',
                    'moved_to_observer': 'send_moved_to_observer_email',
                    'mutual_removal_initiated': 'send_mutual_removal_email',
                    'discussion_archive_warning': 'send_discussion_archive_warning_email',
                    'new_round_started': 'send_new_round_email',
                    'join_request_received': 'send_join_request_email',
                    'reintegration_success': 'send_reintegration_email',
                    'permanent_observer_warning': 'send_permanent_observer_warning_email',
                    'escalation_warning': 'send_escalation_warning_email',
                    'new_response': 'send_new_response_email',
                }
                
                # Try to use templated email if available
                if notification_type in template_map:
                    method_name = template_map[notification_type]
                    method = getattr(EmailService, method_name, None)
                    
                    if method:
                        # Prepare context with user info
                        email_context = {
                            'recipient_email': user.email,
                            'recipient_name': user.get_full_name() or user.username,
                            **context
                        }
                        
                        # Call the appropriate email service method
                        try:
                            method(**email_context)
                            logger.info(f"Templated email sent to {user.email}: {title}")
                            return
                        except TypeError:
                            # Missing required fields, fall through to basic email
                            logger.warning(f"Failed to send templated email, using fallback for {notification_type}")
            
            # Fallback to basic email
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info(f"Email sent to {user.email}: {title}")
        except Exception as e:
            logger.error(f"Failed to send email to {user.email}: {e}")

    @staticmethod
    def _send_push(
        user: User, title: str, message: str, context: Dict[str, Any]
    ) -> None:
        """Send push notification via Firebase Cloud Messaging."""
        try:
            from core.services.fcm_service import FCMService
            
            # Prepare data payload
            data = {
                'notification_type': context.get('notification_type', ''),
                'discussion_id': str(context.get('discussion_id', '')),
                'round_id': str(context.get('round_id', '')),
            }
            
            # Send to all user's active devices
            sent_count = FCMService.send_to_user(user, title, message, data)
            
            if sent_count > 0:
                logger.info(f"Push notification sent to {sent_count} device(s) for {user.username}: {title}")
            else:
                logger.warning(f"No devices available for push notification to {user.username}")
                
        except Exception as e:
            logger.error(f"Failed to send push notification to {user.username}: {e}")

    @staticmethod
    def _push_to_websocket(
        user: User,
        notification_log: NotificationLog,
        notification_type: str,
        title: str,
        message: str,
        context: Dict[str, Any],
        is_critical: bool,
    ) -> None:
        """Push notification to user's WebSocket connection."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"notifications_{user.id}",
                    {
                        "type": "notification_message",
                        "notification_id": str(notification_log.id),
                        "notification_type": notification_type,
                        "title": title,
                        "message": message,
                        "context": context,
                        "is_critical": is_critical,
                        "created_at": notification_log.created_at.isoformat(),
                    },
                )
                logger.info(f"WebSocket notification sent to {user.username}")
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")

    @staticmethod
    @transaction.atomic
    def create_notification_preferences(user: User) -> None:
        """
        Create default notification preferences for new user.

        Args:
            user: User to create preferences for
        """
        for notification_type in NotificationService.ALL_NOTIFICATION_TYPES:
            is_critical = (
                notification_type in NotificationService.CRITICAL_NOTIFICATIONS
            )

            NotificationPreference.objects.get_or_create(
                user=user,
                notification_type=notification_type,
                defaults={
                    "enabled": is_critical,
                    "delivery_method": {"in_app": True, "email": False, "push": False},
                },
            )

        logger.info(f"Notification preferences created for {user.username}")

    @staticmethod
    def send_mrp_expiring_warning(
        user: User, discussion: Discussion, round: Round, percentage_remaining: float
    ) -> None:
        """
        Send warning at 25%, 10%, 5% MRP remaining.

        Args:
            user: User to warn
            discussion: Discussion context
            round: Current round
            percentage_remaining: Percentage of MRP remaining
        """
        # Simple time string based on percentage
        time_str = f"{int(percentage_remaining)}% remaining"

        NotificationService.send_notification(
            user=user,
            notification_type="mrp_expiring_soon",
            context={
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "round_number": round.round_number,
                "time_remaining": time_str,
                "percentage_remaining": percentage_remaining,
            },
            delivery_methods=["in_app", "email"],
        )

    @staticmethod
    def send_discussion_archive_warning(
        discussion: Discussion, current_round: Round
    ) -> None:
        """
        Warn when ≤1 response in round (discussion will archive).

        Args:
            discussion: Discussion that will archive
            current_round: Current round with low responses
        """
        # Get all active participants
        active_participants = discussion.participants.filter(
            role__in=["initiator", "active"]
        )

        for participant in active_participants:
            NotificationService.send_notification(
                user=participant.user,
                notification_type="discussion_will_archive",
                context={
                    "discussion_id": str(discussion.id),
                    "discussion_headline": discussion.topic_headline,
                    "round_number": current_round.round_number,
                },
                delivery_methods=["in_app", "email"],
            )

    @staticmethod
    def send_permanent_observer_warning(
        user: User, discussion: Discussion, votes_against: int
    ) -> None:
        """
        Warn user before vote-based removal finalizes.

        Args:
            user: User facing removal
            discussion: Discussion context
            votes_against: Number of votes against the user
        """
        NotificationService.send_notification(
            user=user,
            notification_type="permanent_observer_warning",
            context={
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "votes_against": votes_against,
            },
            delivery_methods=["in_app", "email"],
        )

    @staticmethod
    def send_mutual_removal_notification(
        initiator: User,
        target: User,
        discussion: Discussion,
        initiator_is_permanent: bool,
        target_is_permanent: bool,
    ) -> None:
        """
        Notify both users of mutual removal.

        Args:
            initiator: User who initiated removal
            target: User who was removed
            discussion: Discussion context
            initiator_is_permanent: Whether initiator became permanent observer
            target_is_permanent: Whether target became permanent observer
        """
        # Notify initiator
        initiator_msg = (
            f"You removed {target.username} from '{discussion.topic_headline}'. "
        )
        if initiator_is_permanent:
            initiator_msg += (
                "You have reached 3 removals and are now a permanent observer."
            )
        else:
            initiator_msg += "Both of you have been moved to temporary observer status."

        NotificationService.send_notification(
            user=initiator,
            notification_type="mutual_removal_initiated",
            context={
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "target_user": target.username,
                "is_permanent": initiator_is_permanent,
                "message": initiator_msg,
            },
            delivery_methods=["in_app", "email"],
        )

        # Notify target
        target_msg = (
            f"{initiator.username} removed you from '{discussion.topic_headline}'. "
        )
        if target_is_permanent:
            target_msg += (
                "You have been removed 3 times and are now a permanent observer."
            )
        else:
            target_msg += "Both of you have been moved to temporary observer status."

        NotificationService.send_notification(
            user=target,
            notification_type="mutual_removal_initiated",
            context={
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "initiator_user": initiator.username,
                "is_permanent": target_is_permanent,
                "message": target_msg,
            },
            delivery_methods=["in_app", "email"],
        )

    @staticmethod
    def send_escalation_warning(user: User, discussion: Discussion, count: int) -> None:
        """
        Warn user approaching 3 removals (permanent observer).

        Args:
            user: User to warn
            discussion: Discussion context
            count: Current removal count
        """
        NotificationService.send_notification(
            user=user,
            notification_type="mutual_removal_escalation_warning",
            context={
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "removal_count": count,
            },
            delivery_methods=["in_app", "email"],
        )

    @staticmethod
    def send_voting_notifications(
        discussion: Discussion, round: Round, event: str
    ) -> None:
        """
        Send voting window opened/closing notifications.

        Args:
            discussion: Discussion context
            round: Round in voting phase
            event: 'opened' or 'closing'
        """
        # Get all participants (active + observers can vote)
        participants = discussion.participants.all()

        notification_type = (
            "voting_window_opened" if event == "opened" else "voting_window_closing"
        )

        for participant in participants:
            context = {
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "round_number": round.round_number,
            }

            if event == "closing":
                context["time_remaining"] = "24 hours"

            NotificationService.send_notification(
                user=participant.user,
                notification_type=notification_type,
                context=context,
                delivery_methods=["in_app"],
            )

    @staticmethod
    def send_join_request_notification(discussion: Discussion, requester: User) -> None:
        """
        Notify discussion creator of join request.

        Args:
            discussion: Discussion being joined
            requester: User requesting to join
        """
        NotificationService.send_notification(
            user=discussion.initiator,
            notification_type="join_request_received",
            context={
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "user_name": requester.username,
                "requester_id": str(requester.id),
            },
            delivery_methods=["in_app", "email"],
        )

    @staticmethod
    def send_moved_to_observer_notification(
        user: User, discussion: Discussion, observer_type: str, reason: str
    ) -> None:
        """
        Notify user they've been moved to observer status.

        Args:
            user: User moved to observer
            discussion: Discussion context
            observer_type: 'temporary_observer' or 'permanent_observer'
            reason: Reason for observer status
        """
        NotificationService.send_notification(
            user=user,
            notification_type="moved_to_observer",
            context={
                "discussion_id": str(discussion.id),
                "discussion_headline": discussion.topic_headline,
                "observer_type": observer_type.replace("_", " "),
                "reason": reason,
            },
            delivery_methods=["in_app", "email"],
        )
