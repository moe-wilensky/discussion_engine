"""
Security and anti-abuse detection service.

Implements rate limiting and behavioral spam detection.
"""

from typing import Dict, List
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Q

from core.models import User, Invite, Response, Discussion


class AbuseDetectionService:
    """
    Detect and prevent abusive behavior.
    """

    # Rate limit configurations
    RATE_LIMITS = {
        "verification_requests": {
            "max_requests": 3,
            "window_seconds": 3600,  # 1 hour
            "key_prefix": "rate_verification:",
        },
        "invite_sends": {
            "max_requests": 10,
            "window_seconds": 3600,  # 1 hour
            "key_prefix": "rate_invite:",
        },
        "join_requests": {
            "max_requests": 5,
            "window_seconds": 3600,  # 1 hour
            "key_prefix": "rate_join:",
        },
        "api_general": {
            "max_requests": 100,
            "window_seconds": 60,  # 1 minute
            "key_prefix": "rate_api:",
        },
    }

    @classmethod
    def check_rate_limit(cls, identifier: str, action: str) -> bool:
        """
        Check if identifier is within rate limit for action.

        Args:
            identifier: Unique identifier (phone number, user ID, etc.)
            action: Action type (matches RATE_LIMITS keys)

        Returns:
            True if within rate limit, False if exceeded
        """
        if action not in cls.RATE_LIMITS:
            return True  # No limit configured

        config = cls.RATE_LIMITS[action]
        key = f"{config['key_prefix']}{identifier}"

        current_count = cache.get(key, 0)

        if current_count >= config["max_requests"]:
            return False

        # Increment counter
        if current_count == 0:
            # First request, set with expiry
            cache.set(key, 1, timeout=config["window_seconds"])
        else:
            # Increment existing counter
            cache.incr(key)

        return True

    @classmethod
    def get_rate_limit_remaining(cls, identifier: str, action: str) -> int:
        """
        Get remaining requests for identifier/action.

        Args:
            identifier: Unique identifier
            action: Action type

        Returns:
            Number of remaining requests
        """
        if action not in cls.RATE_LIMITS:
            return 999  # Unlimited

        config = cls.RATE_LIMITS[action]
        key = f"{config['key_prefix']}{identifier}"

        current_count = cache.get(key, 0)
        return max(0, config["max_requests"] - current_count)

    @classmethod
    def detect_spam_pattern(cls, user: User) -> Dict:
        """
        Behavioral analysis for spam detection.

        Args:
            user: User to analyze

        Returns:
            Dictionary with spam analysis results
        """
        flags = []
        confidence = 0.0

        # Check 1: Too many rapid invites sent
        recent_cutoff = timezone.now() - timedelta(hours=24)
        recent_invites = Invite.objects.filter(
            inviter=user, sent_at__gte=recent_cutoff
        ).count()

        if recent_invites > 20:
            flags.append("excessive_invites_24h")
            confidence += 0.3

        # Check 2: High decline rate
        total_invites = Invite.objects.filter(inviter=user).count()
        if total_invites > 5:
            declined_invites = Invite.objects.filter(
                inviter=user, status="declined"
            ).count()

            decline_rate = declined_invites / total_invites
            if decline_rate > 0.5:  # More than 50% declined
                flags.append("high_decline_rate")
                confidence += 0.4

        # Check 3: No actual participation
        response_count = user.responses.count()
        if total_invites > 0 and response_count == 0:
            flags.append("no_participation")
            confidence += 0.5

        # Check 4: Invite formula violation
        if user.platform_invites_acquired > (
            user.platform_invites_used + user.platform_invites_banked
        ):
            flags.append("invite_formula_violation_platform")
            confidence += 0.8

        if user.discussion_invites_acquired > (
            user.discussion_invites_used + user.discussion_invites_banked
        ):
            flags.append("invite_formula_violation_discussion")
            confidence += 0.8

        # Check 5: Rapid account creation and invite sending
        account_age = timezone.now() - user.created_at
        if account_age < timedelta(hours=1) and recent_invites > 5:
            flags.append("new_account_spam")
            confidence += 0.6

        # Check 6: Multiple flagged responses
        # Note: Response flags would be tracked via ModerationAction
        # For now, skip this check or check moderation actions
        flagged_count = 0
        if flagged_count > 3:
            flags.append("multiple_flagged_responses")
            confidence += 0.5

        # Cap confidence at 1.0
        confidence = min(1.0, confidence)

        is_spam = confidence > 0.7

        return {
            "is_spam": is_spam,
            "confidence": round(confidence, 2),
            "flags": flags,
            "metrics": {
                "recent_invites_24h": recent_invites,
                "total_invites": total_invites,
                "response_count": response_count,
                "account_age_hours": account_age.total_seconds() / 3600,
            },
        }

    @classmethod
    def flag_for_review(cls, user: User, reason: str) -> None:
        """
        Flag user for admin review.

        Args:
            user: User to flag
            reason: Reason for flagging
        """
        if not isinstance(user.behavioral_flags, dict):
            user.behavioral_flags = {}

        if "admin_flags" not in user.behavioral_flags:
            user.behavioral_flags["admin_flags"] = []

        flag_entry = {
            "reason": reason,
            "flagged_at": timezone.now().isoformat(),
            "resolved": False,
        }

        user.behavioral_flags["admin_flags"].append(flag_entry)
        user.save()

    @classmethod
    def is_flagged(cls, user: User) -> bool:
        """
        Check if user has unresolved flags.

        Args:
            user: User to check

        Returns:
            True if user has unresolved flags
        """
        if not isinstance(user.behavioral_flags, dict):
            return False

        admin_flags = user.behavioral_flags.get("admin_flags", [])
        return any(not flag.get("resolved", False) for flag in admin_flags)

    @classmethod
    def detect_multi_account(cls, user: User) -> Dict:
        """
        Multi-account detection.

        Args:
            user: User to analyze

        Returns:
            Dictionary with multi-account detection results
        """
        flags = []
        confidence = 0.0

        # Check 1: Similar phone number patterns
        # Look for users with similar phone numbers (same area code, sequential, etc.)
        user_phone = user.phone_number
        if user_phone:
            # Check for phones with same prefix (first 6 digits)
            if len(user_phone) >= 6:
                prefix = user_phone[:6]
                similar_phones = (
                    User.objects.filter(phone_number__startswith=prefix)
                    .exclude(id=user.id)
                    .count()
                )

                if similar_phones > 0:
                    flags.append("similar_phone_patterns")
                    confidence += 0.3 * min(1.0, similar_phones / 3)

        # Check 2: Behavioral timing correlation
        # Check if user created account shortly after another similar user
        recent_cutoff = user.created_at - timedelta(hours=24)
        nearby_accounts = (
            User.objects.filter(
                created_at__gte=recent_cutoff,
                created_at__lte=user.created_at + timedelta(hours=24),
            )
            .exclude(id=user.id)
            .count()
        )

        if nearby_accounts > 2:
            flags.append("timing_correlation")
            confidence += 0.2

        # Check 3: Similar behavior patterns
        # Check for users with similar response patterns, similar content, etc.
        user_responses = Response.objects.filter(user=user)
        if user_responses.exists():
            user_response_texts = [r.content for r in user_responses[:5]]

            # Check other recent users for similar content
            recent_users = User.objects.filter(
                created_at__gte=user.created_at - timedelta(days=7)
            ).exclude(id=user.id)

            for other_user in recent_users[:10]:  # Limit check to prevent slowdown
                other_responses = Response.objects.filter(user=other_user)[:5]
                other_response_texts = [r.content for r in other_responses]

                # Simple similarity check (could be improved)
                similarity_count = 0
                for user_text in user_response_texts:
                    for other_text in other_response_texts:
                        if (
                            user_text
                            and other_text
                            and len(user_text) > 20
                            and len(other_text) > 20
                        ):
                            # Check for substantial overlap
                            if user_text in other_text or other_text in user_text:
                                similarity_count += 1

                if similarity_count > 2:
                    flags.append("content_similarity")
                    confidence += 0.4
                    break

        # Cap confidence at 1.0
        confidence = min(1.0, confidence)

        is_likely_multi = confidence > 0.7

        return {
            "is_likely_multi": is_likely_multi,
            "confidence": round(confidence, 2),
            "signals": flags,
        }

    @classmethod
    def detect_discussion_spam(cls, user: User) -> Dict:
        """
        Spam discussion creation detection.

        Args:
            user: User to analyze

        Returns:
            Dictionary with spam detection results
        """
        from core.models import Discussion

        flags = []
        confidence = 0.0

        # Check 1: Too many discussions created in short time
        recent_cutoff = timezone.now() - timedelta(hours=24)
        recent_discussions = Discussion.objects.filter(
            initiator=user, created_at__gte=recent_cutoff
        ).count()

        if recent_discussions > 5:
            flags.append("excessive_discussions_24h")
            confidence += 0.4

        # Check 2: Duplicate/near-duplicate topics
        all_discussions = Discussion.objects.filter(initiator=user)
        if all_discussions.count() > 2:
            topics = [d.topic_headline.lower() for d in all_discussions]
            unique_topics = set(topics)

            duplicate_rate = 1 - (len(unique_topics) / len(topics))
            if duplicate_rate > 0.5:
                flags.append("duplicate_topics")
                confidence += 0.5

        # Check 3: No participation after creation
        discussions_with_no_responses = 0
        for discussion in all_discussions:
            user_responses = Response.objects.filter(
                user=user, round__discussion=discussion
            ).count()

            if user_responses == 0:
                discussions_with_no_responses += 1

        if all_discussions.count() > 0:
            no_participation_rate = (
                discussions_with_no_responses / all_discussions.count()
            )
            if no_participation_rate > 0.7:
                flags.append("no_participation_after_creation")
                confidence += 0.6

        # Check 4: Pattern of creating then abandoning
        abandoned_count = Discussion.objects.filter(
            initiator=user, status="archived"
        ).count()

        if all_discussions.count() > 0:
            abandoned_rate = abandoned_count / all_discussions.count()
            if abandoned_rate > 0.8 and all_discussions.count() > 3:
                flags.append("abandonment_pattern")
                confidence += 0.3

        # Cap confidence at 1.0
        confidence = min(1.0, confidence)

        is_spam = confidence > 0.7

        return {
            "is_spam": is_spam,
            "confidence": round(confidence, 2),
            "signals": flags,
        }

    @classmethod
    def detect_response_spam(cls, response: Response) -> Dict:
        """
        Spam response detection.

        Args:
            response: Response to analyze

        Returns:
            Dictionary with spam detection results
        """
        flags = []
        confidence = 0.0

        user = response.user
        content = response.content

        # Check 1: Repetitive content across responses
        user_responses = Response.objects.filter(user=user).exclude(id=response.id)
        if user_responses.count() > 2:
            similar_count = 0
            for other_response in user_responses:
                if other_response.content == content:
                    similar_count += 1
                elif len(content) > 20 and len(other_response.content) > 20:
                    # Check for substantial overlap
                    if (
                        content in other_response.content
                        or other_response.content in content
                    ):
                        similar_count += 1

            if similar_count > 2:
                flags.append("repetitive_content")
                confidence += 0.5

        # Check 2: Copy-paste patterns (very short or very long without variation)
        if len(content) < 10:
            flags.append("too_short")
            confidence += 0.3

        # Check 3: Low-quality/gibberish content
        words = content.split()
        if len(words) > 5:
            # Check for repeated words
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.3:
                flags.append("low_quality_repetitive")
                confidence += 0.4

        # Check 4: External links/promotion (basic check)
        if "http://" in content or "https://" in content or "www." in content:
            flags.append("external_links")
            confidence += 0.6

        # Check for common spam keywords
        spam_keywords = [
            "buy now",
            "click here",
            "limited time",
            "act now",
            "free money",
        ]
        content_lower = content.lower()
        for keyword in spam_keywords:
            if keyword in content_lower:
                flags.append("spam_keywords")
                confidence += 0.7
                break

        # Cap confidence at 1.0
        confidence = min(1.0, confidence)

        is_spam = confidence > 0.7

        return {
            "is_spam": is_spam,
            "confidence": round(confidence, 2),
            "signals": flags,
        }

    @classmethod
    def detect_invitation_abuse(cls, user: User) -> Dict:
        """
        Invitation abuse detection.

        Args:
            user: User to analyze

        Returns:
            Dictionary with abuse detection results
        """
        flags = []
        confidence = 0.0

        # Check 1: Inviting same users repeatedly
        invites_sent = Invite.objects.filter(inviter=user)
        if invites_sent.count() > 5:
            # Count invites per invitee
            from django.db.models import Count

            invitee_counts = (
                invites_sent.values("invitee")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            if invitee_counts.exists():
                max_invites_to_same = invitee_counts[0]["count"]
                if max_invites_to_same > 3:
                    flags.append("repeated_invitations")
                    confidence += 0.5

        # Check 2: Creating discussions just to generate invites
        from core.models import Discussion

        discussions_created = Discussion.objects.filter(initiator=user).count()
        discussion_invites = Invite.objects.filter(
            inviter=user, invite_type="discussion"
        ).count()

        if discussions_created > 0:
            invites_per_discussion = discussion_invites / discussions_created
            if invites_per_discussion > 8:  # More than reasonable participant count
                flags.append("excessive_invites_per_discussion")
                confidence += 0.4

        # Check 3: Circular invitation patterns
        # Check if user invites people who then invite them back
        invites_sent_to = set(invites_sent.values_list("invitee", flat=True))
        invites_received_from = set(
            Invite.objects.filter(invitee=user).values_list("inviter", flat=True)
        )

        circular_count = len(invites_sent_to.intersection(invites_received_from))
        if circular_count > 3:
            flags.append("circular_invitation_pattern")
            confidence += 0.3

        # Check 4: High invite send rate
        recent_cutoff = timezone.now() - timedelta(hours=24)
        recent_invites = Invite.objects.filter(
            inviter=user, sent_at__gte=recent_cutoff
        ).count()

        if recent_invites > 15:
            flags.append("high_invite_rate")
            confidence += 0.4

        # Cap confidence at 1.0
        confidence = min(1.0, confidence)

        is_abuse = confidence > 0.7

        return {
            "is_abuse": is_abuse,
            "confidence": round(confidence, 2),
            "signals": flags,
        }

    @classmethod
    def calculate_user_risk_score(cls, user: User) -> Dict:
        """
        Comprehensive risk assessment.

        Args:
            user: User to assess

        Returns:
            Dictionary with risk level and breakdown
        """
        # Run all detection methods
        spam_detection = cls.detect_spam_pattern(user)
        multi_account_detection = cls.detect_multi_account(user)
        discussion_spam_detection = cls.detect_discussion_spam(user)
        invitation_abuse_detection = cls.detect_invitation_abuse(user)

        # Weight each detection type
        weights = {
            "spam": 0.3,
            "multi_account": 0.3,
            "discussion_spam": 0.2,
            "invitation_abuse": 0.2,
        }

        # Calculate weighted score
        overall_score = (
            spam_detection.get("confidence", 0) * weights["spam"]
            + multi_account_detection.get("confidence", 0) * weights["multi_account"]
            + discussion_spam_detection.get("confidence", 0)
            * weights["discussion_spam"]
            + invitation_abuse_detection.get("confidence", 0)
            * weights["invitation_abuse"]
        )

        # Determine risk level
        if overall_score < 0.3:
            risk_level = "low"
        elif overall_score < 0.7:
            risk_level = "medium"
        else:
            risk_level = "high"

        return {
            "risk_level": risk_level,
            "overall_score": round(overall_score, 2),
            "breakdown": {
                "spam": spam_detection.get("confidence", 0),
                "multi_account": multi_account_detection.get("confidence", 0),
                "discussion_spam": discussion_spam_detection.get("confidence", 0),
                "invitation_abuse": invitation_abuse_detection.get("confidence", 0),
            },
            "all_signals": {
                "spam": spam_detection.get("flags", []),
                "multi_account": multi_account_detection.get("signals", []),
                "discussion_spam": discussion_spam_detection.get("signals", []),
                "invitation_abuse": invitation_abuse_detection.get("signals", []),
            },
        }

    @classmethod
    def auto_moderate(cls, user: User) -> Dict:
        """
        Automatic moderation based on abuse scores.

        Args:
            user: User to moderate

        Returns:
            Dictionary with action taken and reason
        """
        risk_assessment = cls.calculate_user_risk_score(user)
        overall_score = risk_assessment["overall_score"]

        action_taken = None
        reason = None

        # High confidence (>0.9) + high risk: auto-ban
        if overall_score >= 0.9:
            from core.models import UserBan, AdminFlag
            from core.services.notification_service import NotificationService

            # Create ban
            ban = UserBan.objects.create(
                user=user,
                banned_by=None,  # System ban
                reason="Automatic ban due to high abuse score",
                is_permanent=False,
                duration_days=7,  # Temporary ban for review
            )

            # Disable user
            user.is_active = False
            user.save()

            # Create flag for admin review
            AdminFlag.objects.create(
                user=user,
                flagged_by=None,
                reason=f"Auto-moderation: Risk score {overall_score}",
                detection_type="auto_ban",
                confidence=overall_score,
                signals=risk_assessment["all_signals"],
            )

            # Notify admins
            admin_users = User.objects.filter(is_staff=True)
            for admin in admin_users:
                NotificationService.send_notification(
                    user=admin,
                    notification_type="auto_ban",
                    title="User Auto-Banned",
                    message=f"{user.username} was automatically banned (score: {overall_score})",
                    context={"user_id": str(user.id), "score": overall_score},
                )

            action_taken = "auto_ban"
            reason = f"High risk score: {overall_score}"

        # Medium confidence (0.7-0.9): flag for admin review
        elif overall_score >= 0.7:
            from core.models import AdminFlag
            from core.services.notification_service import NotificationService

            # Create flag
            AdminFlag.objects.create(
                user=user,
                flagged_by=None,
                reason=f"Auto-detection: Risk score {overall_score}",
                detection_type="auto_flag",
                confidence=overall_score,
                signals=risk_assessment["all_signals"],
            )

            # Notify admins
            admin_users = User.objects.filter(is_staff=True)
            for admin in admin_users:
                NotificationService.send_notification(
                    user=admin,
                    notification_type="auto_flag",
                    title="User Flagged for Review",
                    message=f"{user.username} flagged for suspicious activity (score: {overall_score})",
                    context={"user_id": str(user.id), "score": overall_score},
                )

            action_taken = "flagged_for_review"
            reason = f"Medium risk score: {overall_score}"

        # Low confidence (<0.7): log for monitoring
        else:
            # Just log - no action needed
            action_taken = "monitored"
            reason = f"Low risk score: {overall_score}"

        return {
            "action_taken": action_taken,
            "reason": reason,
            "risk_score": overall_score,
        }

    @classmethod
    def get_abuse_patterns(cls) -> Dict:
        """
        Platform-wide abuse pattern analysis.

        Returns:
            Dictionary with common abuse patterns and trends
        """
        from core.models import AdminFlag

        # Get recent flags
        recent_cutoff = timezone.now() - timedelta(days=30)
        recent_flags = AdminFlag.objects.filter(created_at__gte=recent_cutoff)

        # Count by detection type
        detection_counts = {}
        for flag in recent_flags:
            dtype = flag.detection_type or "manual"
            detection_counts[dtype] = detection_counts.get(dtype, 0) + 1

        # Get common signals
        all_signals = []
        for flag in recent_flags:
            if flag.signals:
                all_signals.extend(flag.signals)

        signal_counts = {}
        for signal in all_signals:
            signal_counts[signal] = signal_counts.get(signal, 0) + 1

        # Sort by frequency
        top_signals = sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]

        return {
            "detection_type_counts": detection_counts,
            "top_signals": dict(top_signals),
            "total_flags_30_days": recent_flags.count(),
            "analysis_period": "30 days",
        }
