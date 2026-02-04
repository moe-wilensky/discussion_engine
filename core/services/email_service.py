"""
Email service for rendering and sending HTML emails.

Handles email template rendering and delivery for all notification types.
"""

from typing import Dict, Optional
import logging
from django.core.mail import send_mail, EmailMultiAlternatives
from django.core.validators import validate_email as django_validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.core.cache import cache

logger = logging.getLogger(__name__)


class EmailService:
    """Service for rendering and sending emails with templates."""

    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Validate email address format.

        Args:
            email: Email address to validate

        Returns:
            bool: True if email is valid, False otherwise
        """
        try:
            django_validate_email(email)
            return True
        except ValidationError:
            logger.error(f"Invalid email address format: {email[:3]}***@***")
            return False

    @staticmethod
    def check_rate_limit(recipient_email: str) -> bool:
        """
        Check if email rate limit has been exceeded.

        Args:
            recipient_email: Recipient's email address

        Returns:
            bool: True if within rate limit, False if exceeded
        """
        # Get rate limit from settings (default: 10 emails per hour)
        rate_limit = getattr(settings, 'EMAIL_RATE_LIMIT', 10)

        # Create cache key for this recipient
        cache_key = f"email_rate_limit:{recipient_email}"

        # Get current count from cache
        current_count = cache.get(cache_key, 0)

        if current_count >= rate_limit:
            logger.warning(f"Email rate limit exceeded for recipient: {recipient_email[:3]}***@***")
            return False

        # Increment count and set to expire in 1 hour
        cache.set(cache_key, current_count + 1, 3600)
        return True

    @staticmethod
    def send_email(
        recipient_email: str,
        subject: str,
        template_name: str,
        context: Dict,
        from_email: Optional[str] = None
    ) -> bool:
        """
        Send an HTML email using a template.

        Args:
            recipient_email: Recipient's email address
            subject: Email subject line
            template_name: Name of the template (e.g., 'discussion_invite')
            context: Context dictionary for template rendering
            from_email: Sender email (defaults to settings.DEFAULT_FROM_EMAIL)

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        # Validate email address
        if not EmailService.validate_email(recipient_email):
            logger.error(f"Failed to send email: invalid email address")
            return False

        # Check rate limiting
        if not EmailService.check_rate_limit(recipient_email):
            logger.warning(f"Failed to send email: rate limit exceeded for recipient")
            return False

        if from_email is None:
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@discussionplatform.com')

        try:
            # Build template path
            template_path = f'email/notifications/{template_name}.html'

            # Render HTML email
            html_content = render_to_string(template_path, context)

            # Create plain text version by stripping HTML
            text_content = strip_tags(html_content)

            # Create email with both HTML and plain text versions
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[recipient_email]
            )
            email.attach_alternative(html_content, "text/html")

            # Send email
            email.send(fail_silently=False)

            logger.info(f"Email sent successfully to {recipient_email[:3]}***@*** - Subject: {subject}")
            return True

        except Exception as e:
            logger.error(f"Error sending email to {recipient_email[:3]}***@***: {e}")
            return False

    @staticmethod
    def send_discussion_invite(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        initiator_name: str,
        participant_count: int,
        action_url: str
    ) -> bool:
        """Send discussion invitation email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'initiator_name': initiator_name,
            'participant_count': participant_count,
            'action_url': action_url,
            'action_text': 'View Invitation',
            'title': 'Discussion Invitation'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'You\'ve been invited to discuss: {topic}',
            template_name='discussion_invite',
            context=context
        )

    @staticmethod
    def send_mrp_expiring_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        hours_remaining: int,
        action_url: str
    ) -> bool:
        """Send MRP expiring warning email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'hours_remaining': hours_remaining,
            'action_url': action_url,
            'action_text': 'Submit Response',
            'title': 'Response Deadline Approaching'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'Deadline approaching: {topic}',
            template_name='mrp_expiring',
            context=context
        )

    @staticmethod
    def send_voting_started_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        vote_question: str,
        voting_deadline: str,
        action_url: str
    ) -> bool:
        """Send voting started email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'vote_question': vote_question,
            'voting_deadline': voting_deadline,
            'action_url': action_url,
            'action_text': 'Cast Your Vote',
            'title': 'Voting Has Begun'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'Vote now: {topic}',
            template_name='voting_started',
            context=context
        )

    @staticmethod
    def send_moved_to_observer_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        reason: str,
        can_rejoin: bool,
        wait_period: Optional[str] = None,
        action_url: Optional[str] = None
    ) -> bool:
        """Send moved to observer notification email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'reason': reason,
            'can_rejoin': can_rejoin,
            'wait_period': wait_period,
            'action_url': action_url,
            'action_text': 'View Discussion',
            'title': 'Discussion Status Update'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'Status change in: {topic}',
            template_name='moved_to_observer',
            context=context
        )

    @staticmethod
    def send_mutual_removal_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        action_url: str
    ) -> bool:
        """Send mutual removal initiated email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'action_url': action_url,
            'action_text': 'View Discussion',
            'title': 'Mutual Removal Initiated'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'Moderation action in: {topic}',
            template_name='mutual_removal_initiated',
            context=context
        )

    @staticmethod
    def send_discussion_archive_warning_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        days_remaining: int,
        action_url: str
    ) -> bool:
        """Send discussion archive warning email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'days_remaining': days_remaining,
            'action_url': action_url,
            'action_text': 'View Discussion',
            'title': 'Discussion Archiving Soon'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'Discussion archiving soon: {topic}',
            template_name='discussion_archive_warning',
            context=context
        )

    @staticmethod
    def send_new_round_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        round_number: int,
        action_url: str
    ) -> bool:
        """Send new round started email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'round_number': round_number,
            'action_url': action_url,
            'action_text': 'View New Round',
            'title': 'New Discussion Round'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'New round in: {topic}',
            template_name='new_round_started',
            context=context
        )

    @staticmethod
    def send_join_request_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        requester_name: str,
        request_message: str,
        action_url: str
    ) -> bool:
        """Send join request received email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'requester_name': requester_name,
            'request_message': request_message,
            'action_url': action_url,
            'action_text': 'Review Request',
            'title': 'Join Request Received'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'Join request for: {topic}',
            template_name='join_request_received',
            context=context
        )

    @staticmethod
    def send_reintegration_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        action_url: str
    ) -> bool:
        """Send reintegration success email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'action_url': action_url,
            'action_text': 'Return to Discussion',
            'title': 'Welcome Back!'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'You\'re back in: {topic}',
            template_name='reintegration_success',
            context=context
        )

    @staticmethod
    def send_permanent_observer_warning_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        action_url: str
    ) -> bool:
        """Send permanent observer warning email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'action_url': action_url,
            'action_text': 'View Guidelines',
            'title': 'Important Warning'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'Warning: {topic}',
            template_name='permanent_observer_warning',
            context=context
        )

    @staticmethod
    def send_escalation_warning_email(
        recipient_email: str,
        recipient_name: str,
        count: int
    ) -> bool:
        """Send escalation warning email."""
        context = {
            'recipient_name': recipient_name,
            'count': count,
            'title': 'Account Warning'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject='Important account notice',
            template_name='escalation_warning',
            context=context
        )

    @staticmethod
    def send_new_response_email(
        recipient_email: str,
        recipient_name: str,
        topic: str,
        author_name: str,
        round_number: int,
        action_url: str
    ) -> bool:
        """Send new response notification email."""
        context = {
            'recipient_name': recipient_name,
            'topic': topic,
            'author_name': author_name,
            'round_number': round_number,
            'action_url': action_url,
            'action_text': 'Read Response',
            'title': 'New Response'
        }

        return EmailService.send_email(
            recipient_email=recipient_email,
            subject=f'New response in: {topic}',
            template_name='new_response',
            context=context
        )
