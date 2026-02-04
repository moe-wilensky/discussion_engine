"""
Django signals for automated abuse detection.

Automatically triggers security checks when users perform certain actions.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Invite, Response, Discussion
from core.security.abuse_detection import AbuseDetectionService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Invite)
def check_invite_abuse(sender, instance, created, **kwargs):
    """
    Automatically check for invitation abuse when invites are sent.

    Triggers:
    - When a new invite is created
    - Checks for excessive invite sending, circular patterns, etc.
    """
    if not created:
        return  # Only check on creation, not updates

    user = instance.inviter
    if not user:
        return

    try:
        # Check for invitation abuse patterns
        abuse_result = AbuseDetectionService.detect_invitation_abuse(user)

        if abuse_result.get("is_abuse"):
            logger.warning(
                f"Invitation abuse detected for user {user.username} (ID: {user.id}). "
                f"Confidence: {abuse_result.get('confidence')}, "
                f"Signals: {abuse_result.get('signals')}"
            )

            # Flag user for review if confidence is high
            if abuse_result.get("confidence", 0) >= 0.7:
                AbuseDetectionService.flag_for_review(
                    user,
                    f"Invitation abuse detected: {', '.join(abuse_result.get('signals', []))}"
                )

        # Also check overall spam pattern
        spam_result = AbuseDetectionService.detect_spam_pattern(user)

        if spam_result.get("is_spam"):
            logger.warning(
                f"Spam pattern detected for user {user.username} (ID: {user.id}). "
                f"Confidence: {spam_result.get('confidence')}, "
                f"Flags: {spam_result.get('flags')}"
            )

            # Auto-moderate if confidence is very high
            if spam_result.get("confidence", 0) >= 0.8:
                moderation_result = AbuseDetectionService.auto_moderate(user)
                logger.info(
                    f"Auto-moderation action for user {user.username}: "
                    f"{moderation_result.get('action_taken')} - {moderation_result.get('reason')}"
                )

    except Exception as e:
        logger.exception(f"Error checking invite abuse for user {user.id}: {e}")


@receiver(post_save, sender=Response)
def check_response_abuse(sender, instance, created, **kwargs):
    """
    Automatically check for response spam when responses are posted.

    Triggers:
    - When a new response is created
    - Checks for repetitive content, spam keywords, etc.
    """
    if not created:
        return  # Only check on creation, not edits

    user = instance.user
    if not user:
        return

    try:
        # Check response for spam
        spam_result = AbuseDetectionService.detect_response_spam(instance)

        if spam_result.get("is_spam"):
            logger.warning(
                f"Spam response detected from user {user.username} (ID: {user.id}). "
                f"Response ID: {instance.id}, "
                f"Confidence: {spam_result.get('confidence')}, "
                f"Signals: {spam_result.get('signals')}"
            )

            # Flag user for review if confidence is high
            if spam_result.get("confidence", 0) >= 0.7:
                AbuseDetectionService.flag_for_review(
                    user,
                    f"Spam response detected: {', '.join(spam_result.get('signals', []))}"
                )

        # Also check general spam pattern
        user_spam_result = AbuseDetectionService.detect_spam_pattern(user)

        if user_spam_result.get("is_spam"):
            # Auto-moderate if confidence is very high
            if user_spam_result.get("confidence", 0) >= 0.8:
                moderation_result = AbuseDetectionService.auto_moderate(user)
                logger.info(
                    f"Auto-moderation action for user {user.username}: "
                    f"{moderation_result.get('action_taken')} - {moderation_result.get('reason')}"
                )

    except Exception as e:
        logger.exception(f"Error checking response abuse for user {user.id}: {e}")


@receiver(post_save, sender=Discussion)
def check_discussion_abuse(sender, instance, created, **kwargs):
    """
    Automatically check for discussion spam when discussions are created.

    Triggers:
    - When a new discussion is created
    - Checks for excessive discussion creation, duplicate topics, etc.
    """
    if not created:
        return  # Only check on creation, not updates

    user = instance.initiator
    if not user:
        return

    try:
        # Check for discussion spam
        spam_result = AbuseDetectionService.detect_discussion_spam(user)

        if spam_result.get("is_spam"):
            logger.warning(
                f"Discussion spam detected from user {user.username} (ID: {user.id}). "
                f"Discussion ID: {instance.id}, "
                f"Confidence: {spam_result.get('confidence')}, "
                f"Signals: {spam_result.get('signals')}"
            )

            # Flag user for review if confidence is high
            if spam_result.get("confidence", 0) >= 0.7:
                AbuseDetectionService.flag_for_review(
                    user,
                    f"Discussion spam detected: {', '.join(spam_result.get('signals', []))}"
                )

        # Check overall user pattern
        user_spam_result = AbuseDetectionService.detect_spam_pattern(user)

        if user_spam_result.get("is_spam"):
            # Auto-moderate if confidence is very high
            if user_spam_result.get("confidence", 0) >= 0.8:
                moderation_result = AbuseDetectionService.auto_moderate(user)
                logger.info(
                    f"Auto-moderation action for user {user.username}: "
                    f"{moderation_result.get('action_taken')} - {moderation_result.get('reason')}"
                )

    except Exception as e:
        logger.exception(f"Error checking discussion abuse for user {user.id}: {e}")
