"""
User onboarding service for first-time user experience.

Manages tutorial content and curated discussion recommendations.
"""

from typing import List
from django.db.models import QuerySet, Count, Q
from django.utils import timezone
from datetime import timedelta

from core.models import User, Discussion


class OnboardingService:
    """
    First-time user experience and tutorial management.
    """

    @staticmethod
    def get_tutorial_steps() -> List[dict]:
        """
        Return onboarding tutorial content.

        Returns:
            List of tutorial step dictionaries
        """
        return [
            {
                "step": 1,
                "title": "Welcome to Discussion Engine",
                "content": (
                    "Discussion Engine is a platform for meaningful, structured conversations. "
                    "Participate in multi-round discussions with thoughtful peers."
                ),
                "media": None,
            },
            {
                "step": 2,
                "title": "How Discussions Work",
                "content": (
                    "Each discussion has multiple rounds. In each round, you'll submit a response, "
                    "then vote on others' responses. The best responses help guide the conversation forward."
                ),
                "media": None,
            },
            {
                "step": 3,
                "title": "Earning Invites",
                "content": (
                    "You earn invites by participating! Submit thoughtful responses to earn both "
                    "platform invites (for new users) and discussion invites (for existing users)."
                ),
                "media": None,
            },
            {
                "step": 4,
                "title": "Response Quality Matters",
                "content": (
                    "Take your time crafting responses. Quality discussions require effort. "
                    "There are minimum response times and lengths to ensure thoughtful participation."
                ),
                "media": None,
            },
            {
                "step": 5,
                "title": "Multi-Round Process (MRP)",
                "content": (
                    "After initial responses, discussions enter multi-round process. "
                    "Each round builds on previous ones, with voting determining which responses advance."
                ),
                "media": None,
            },
            {
                "step": 6,
                "title": "Moderation & Safety",
                "content": (
                    "Our community maintains high standards. Responses may be flagged and reviewed. "
                    "Be respectful, constructive, and follow community guidelines."
                ),
                "media": None,
            },
            {
                "step": 7,
                "title": "Ready to Start!",
                "content": (
                    "You're ready to join your first discussion! Browse suggested discussions below "
                    "or wait for an invite from a friend."
                ),
                "media": None,
            },
        ]

    @staticmethod
    def get_suggested_discussions(user: User) -> QuerySet:
        """
        Curate discussions for new users.

        Args:
            user: User to get suggestions for

        Returns:
            QuerySet of recommended Discussion objects
        """
        from core.models import PlatformConfig

        config = PlatformConfig.objects.get(pk=1)

        # Get active discussions welcoming newcomers
        recent_cutoff = timezone.now() - timedelta(days=7)

        # Active discussions with available slots
        active_discussions = (
            Discussion.objects.filter(status="active")
            .annotate(participant_count=Count("participants"))
            .filter(
                participant_count__lt=config.max_discussion_participants,
                created_at__gte=recent_cutoff,
            )
            .order_by("-created_at")[:10]
        )

        # Recently archived high-quality discussions (for reading)
        archived_discussions = (
            Discussion.objects.filter(status="archived")
            .annotate(response_count=Count("rounds__responses"))
            .filter(
                response_count__gte=10,  # At least 10 quality responses
                archived_at__gte=recent_cutoff,
            )
            .order_by("-archived_at")[:5]
        )

        # Combine and return
        all_discussions = list(active_discussions) + list(archived_discussions)

        # Return as QuerySet of IDs
        discussion_ids = [d.id for d in all_discussions]
        return Discussion.objects.filter(id__in=discussion_ids)

    @staticmethod
    def mark_tutorial_complete(user: User) -> None:
        """
        Track tutorial completion.

        Args:
            user: User who completed tutorial
        """
        user.tutorial_completed = True
        
        # Also store in behavioral_flags for backwards compatibility
        if not isinstance(user.behavioral_flags, dict):
            user.behavioral_flags = {}

        user.behavioral_flags["tutorial_completed"] = True
        user.behavioral_flags["tutorial_completed_at"] = timezone.now().isoformat()
        user.save()

    @staticmethod
    def has_completed_tutorial(user: User) -> bool:
        """
        Check if user has completed tutorial.

        Args:
            user: User to check

        Returns:
            True if tutorial completed
        """
        return user.tutorial_completed
