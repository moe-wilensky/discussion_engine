"""
Admin service for platform administration.

Provides functionality for platform configuration, user management,
analytics, moderation, and administrative operations.
"""

from typing import Dict, List, Optional
from datetime import timedelta

from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError

from core.models import (
    User,
    PlatformConfig,
    Discussion,
    DiscussionParticipant,
    Response,
    Invite,
    ModerationAction,
    AdminFlag,
    UserBan,
    NotificationLog,
)
from core.services.audit_service import AuditService
from core.services.notification_service import NotificationService


class AdminService:
    """Platform administration functionality."""

    @staticmethod
    def update_platform_config(admin: User, updates: dict) -> PlatformConfig:
        """
        Update platform configuration variables.

        Args:
            admin: Admin user performing update
            updates: Dictionary of field names to new values

        Returns:
            Updated PlatformConfig instance

        Raises:
            PermissionDenied: If user is not superuser
            ValidationError: If invalid values provided
        """
        if not admin.is_superuser:
            raise PermissionDenied("Only superusers can update platform configuration")

        config = PlatformConfig.load()
        changes = []

        # Valid field mappings with type validation
        valid_fields = {
            "new_user_platform_invites": int,
            "new_user_discussion_invites": int,
            "responses_to_unlock_invites": int,
            "responses_per_platform_invite": int,
            "responses_per_discussion_invite": int,
            "max_discussion_participants": int,
            "n_responses_before_mrp": int,
            "max_headline_length": int,
            "max_topic_length": int,
            "voting_increment_percentage": int,
            "vote_based_removal_threshold": float,
            "max_discussion_duration_days": int,
            "max_discussion_rounds": int,
            "max_discussion_responses": int,
            "round_1_phase_1_timeout_days": int,
            "response_edit_percentage": int,
            "response_edit_limit": int,
            "rtm_min": float,
            "rtm_max": float,
            "mrm_min_minutes": int,
            "mrm_max_minutes": int,
            "mrl_min_chars": int,
            "mrl_max_chars": int,
        }

        for field, new_value in updates.items():
            if field not in valid_fields:
                raise ValidationError(f"Invalid field: {field}")

            # Type validation
            expected_type = valid_fields[field]
            if not isinstance(new_value, expected_type):
                try:
                    new_value = expected_type(new_value)
                except (ValueError, TypeError):
                    raise ValidationError(
                        f"Invalid type for {field}: expected {expected_type.__name__}"
                    )

            # Range validation (basic)
            if expected_type == int and new_value < 0:
                raise ValidationError(
                    f"Invalid value for {field}: must be non-negative"
                )

            old_value = getattr(config, field)
            if old_value != new_value:
                setattr(config, field, new_value)
                changes.append({"field": field, "old": old_value, "new": new_value})

        if changes:
            config.save()

            # Audit log
            AuditService.log_admin_action(
                admin=admin,
                action_type="update_platform_config",
                target_type="config",
                target_id="1",
                details={"changes": changes},
                reason="Platform configuration update",
            )

            # Notify all admins
            admin_users = User.objects.filter(is_staff=True)
            for admin_user in admin_users:
                NotificationService.send_notification(
                    user=admin_user,
                    notification_type="config_updated",
                    title="Platform Configuration Updated",
                    message=f"{admin.username} updated {len(changes)} configuration value(s)",
                    context={"changes": changes},
                )

        return config

    @staticmethod
    def get_platform_analytics() -> dict:
        """
        Platform health metrics.

        Returns:
            Dictionary with comprehensive platform analytics
        """
        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # User metrics
        total_users = User.objects.count()
        active_7_days = User.objects.filter(last_login__gte=seven_days_ago).count()
        active_30_days = User.objects.filter(last_login__gte=thirty_days_ago).count()
        new_this_week = User.objects.filter(created_at__gte=seven_days_ago).count()

        # Ban metrics
        banned_users = User.objects.filter(bans__is_active=True).distinct().count()

        # Flag metrics
        flagged_users = (
            AdminFlag.objects.filter(status="pending").values("user").distinct().count()
        )

        # Discussion metrics
        total_discussions = Discussion.objects.count()
        active_discussions = Discussion.objects.filter(status="active").count()
        archived_discussions = Discussion.objects.filter(status="archived").count()

        # Calculate average duration for archived discussions
        archived_with_duration = Discussion.objects.filter(
            status="archived", archived_at__isnull=False
        )
        if archived_with_duration.exists():
            durations = [
                (d.archived_at - d.created_at).days for d in archived_with_duration
            ]
            avg_duration_days = sum(durations) / len(durations)
        else:
            avg_duration_days = 0

        # Calculate average rounds
        from core.models import Round

        discussions_with_rounds = Discussion.objects.annotate(
            round_count=Count("rounds")
        )
        if discussions_with_rounds.exists():
            avg_rounds = (
                discussions_with_rounds.aggregate(avg=Avg("round_count"))["avg"] or 0
            )
        else:
            avg_rounds = 0

        # Completion rate (archived / total)
        completion_rate = (
            archived_discussions / total_discussions if total_discussions > 0 else 0
        )

        # Engagement metrics
        total_responses = Response.objects.count()
        responses_per_user_avg = total_responses / total_users if total_users > 0 else 0

        total_invites_issued = Invite.objects.count()
        total_invites_banked = User.objects.aggregate(total=Count("id"))
        # Calculate actual banked invites
        platform_invites_banked = sum(
            u.platform_invites_banked for u in User.objects.all()
        )
        discussion_invites_banked = sum(
            u.discussion_invites_banked for u in User.objects.all()
        )
        total_banked = platform_invites_banked + discussion_invites_banked

        # Moderation metrics
        mutual_removals = ModerationAction.objects.filter(
            action_type="mutual_removal"
        ).count()

        vote_based_removals = ModerationAction.objects.filter(
            action_type="vote_based_removal"
        ).count()

        permanent_observers = DiscussionParticipant.objects.filter(
            role="permanent_observer"
        ).count()

        active_flags = AdminFlag.objects.filter(status="pending").count()
        resolved_flags = AdminFlag.objects.filter(status="resolved").count()

        # Abuse metrics (will be populated by abuse detection)
        # For now, use basic counts
        spam_flags = AdminFlag.objects.filter(
            detection_type="spam", status="pending"
        ).count()

        multi_account_flags = AdminFlag.objects.filter(
            detection_type="multi_account", status="pending"
        ).count()

        auto_bans = UserBan.objects.filter(
            banned_by__isnull=True  # System bans
        ).count()

        return {
            "users": {
                "total": total_users,
                "active_7_days": active_7_days,
                "active_30_days": active_30_days,
                "new_this_week": new_this_week,
                "banned": banned_users,
                "flagged": flagged_users,
            },
            "discussions": {
                "total": total_discussions,
                "active": active_discussions,
                "archived": archived_discussions,
                "avg_duration_days": round(avg_duration_days, 1),
                "avg_rounds": round(avg_rounds, 1),
                "completion_rate": round(completion_rate, 2),
            },
            "engagement": {
                "total_responses": total_responses,
                "responses_per_user_avg": round(responses_per_user_avg, 1),
                "total_invites_issued": total_invites_issued,
                "total_invites_banked": total_banked,
            },
            "moderation": {
                "mutual_removals": mutual_removals,
                "vote_based_removals": vote_based_removals,
                "permanent_observers": permanent_observers,
                "active_flags": active_flags,
                "resolved_flags": resolved_flags,
            },
            "abuse": {
                "spam_detections": spam_flags,
                "multi_account_detections": multi_account_flags,
                "auto_bans": auto_bans,
            },
        }

    @staticmethod
    def get_user_analytics(user: User) -> dict:
        """
        Individual user analytics.

        Args:
            user: User to analyze

        Returns:
            Dictionary with comprehensive user analytics
        """
        # Participation metrics
        discussions_joined = DiscussionParticipant.objects.filter(user=user).count()

        responses_posted = Response.objects.filter(user=user).count()

        if responses_posted > 0:
            response_lengths = [
                len(r.content) for r in Response.objects.filter(user=user)
            ]
            avg_response_length = sum(response_lengths) / len(response_lengths)
        else:
            avg_response_length = 0

        # Voting participation (how often user votes when eligible)
        from core.models import Vote, Round

        # This is simplified - would need more complex logic for actual rate
        total_votes = Vote.objects.filter(user=user).count()
        voting_participation_rate = min(1.0, total_votes / max(1, discussions_joined))

        # Moderation metrics
        removals_initiated = ModerationAction.objects.filter(
            initiator=user, action_type="mutual_removal"
        ).count()

        times_removed = DiscussionParticipant.objects.filter(
            user=user, role="permanent_observer"
        ).count()

        permanent_observer_discussions = DiscussionParticipant.objects.filter(
            user=user, role="permanent_observer"
        ).count()

        flags_received = AdminFlag.objects.filter(user=user).count()

        # Invitation metrics
        platform_invites_acquired = user.platform_invites_acquired
        platform_invites_used = user.platform_invites_used
        discussion_invites_sent = Invite.objects.filter(
            inviter=user, invite_type="discussion"
        ).count()
        discussion_invites_accepted = Invite.objects.filter(
            inviter=user, invite_type="discussion", status="accepted"
        ).count()

        # Abuse score (from AbuseDetectionService)
        from core.security.abuse_detection import AbuseDetectionService

        spam_detection = AbuseDetectionService.detect_spam_pattern(user)

        return {
            "user": {
                "id": str(user.id),
                "username": user.username,
                "phone_verified": user.phone_verified,
                "created_at": user.created_at.isoformat(),
                "is_banned": user.is_banned(),
            },
            "participation": {
                "discussions_joined": discussions_joined,
                "responses_posted": responses_posted,
                "avg_response_length": round(avg_response_length, 0),
                "voting_participation_rate": round(voting_participation_rate, 2),
            },
            "moderation": {
                "removals_initiated": removals_initiated,
                "times_removed": times_removed,
                "permanent_observer_discussions": permanent_observer_discussions,
                "flags_received": flags_received,
            },
            "invitations": {
                "platform_invites_acquired": platform_invites_acquired,
                "platform_invites_used": platform_invites_used,
                "discussion_invites_sent": discussion_invites_sent,
                "discussion_invites_accepted": discussion_invites_accepted,
            },
            "abuse_score": {
                "spam_score": spam_detection.get("confidence", 0),
                "multi_account_score": 0.0,  # Placeholder
                "overall_risk": (
                    "low"
                    if spam_detection.get("confidence", 0) < 0.5
                    else (
                        "medium"
                        if spam_detection.get("confidence", 0) < 0.8
                        else "high"
                    )
                ),
            },
        }

    @staticmethod
    def flag_user(
        admin: User,
        user: User,
        reason: str,
        detection_type: Optional[str] = None,
        confidence: Optional[float] = None,
        signals: Optional[List[str]] = None,
    ) -> AdminFlag:
        """
        Flag user for review (spam, abuse).

        Args:
            admin: Admin flagging the user (or None for system)
            user: User to flag
            reason: Reason for flagging
            detection_type: Type of detection (spam, multi_account, etc.)
            confidence: Confidence score (0.0 to 1.0)
            signals: List of detection signals

        Returns:
            Created AdminFlag instance
        """
        flag = AdminFlag.objects.create(
            user=user,
            flagged_by=admin,
            reason=reason,
            detection_type=detection_type,
            confidence=confidence,
            signals=signals or [],
        )

        # Audit log
        AuditService.log_admin_action(
            admin=admin or user,  # Use user as admin for system flags
            action_type="flag_user",
            target_type="user",
            target_id=str(user.id),
            details={
                "reason": reason,
                "detection_type": detection_type,
                "confidence": confidence,
            },
            reason=reason,
        )

        # Notify admin team
        admin_users = User.objects.filter(is_staff=True)
        for admin_user in admin_users:
            NotificationService.send_notification(
                user=admin_user,
                notification_type="user_flagged",
                title="User Flagged for Review",
                message=f"{user.username} has been flagged: {reason}",
                context={
                    "flag_id": str(flag.id),
                    "user_id": str(user.id),
                    "username": user.username,
                    "reason": reason,
                },
            )

        return flag

    @staticmethod
    def ban_user(
        admin: User, user: User, reason: str, duration_days: Optional[int] = None
    ) -> UserBan:
        """
        Ban user account.

        Args:
            admin: Admin banning the user
            user: User to ban
            reason: Reason for ban
            duration_days: Number of days for temporary ban (None = permanent)

        Returns:
            Created UserBan instance
        """
        if not admin.is_staff:
            raise PermissionDenied("Only staff can ban users")

        # Check if already banned
        if user.is_banned():
            raise ValidationError("User is already banned")

        # Calculate expiry for temporary ban
        expires_at = None
        if duration_days is not None:
            expires_at = timezone.now() + timedelta(days=duration_days)

        # Create ban record
        ban = UserBan.objects.create(
            user=user,
            banned_by=admin,
            reason=reason,
            is_permanent=(duration_days is None),
            duration_days=duration_days,
            expires_at=expires_at,
        )

        # Disable authentication
        user.is_active = False
        user.save()

        # Move to permanent observer in all active discussions
        active_participants = DiscussionParticipant.objects.filter(
            user=user, discussion__status="active", role__in=["initiator", "active"]
        )

        for participant in active_participants:
            participant.role = "permanent_observer"
            participant.save()

        # Audit log
        AuditService.log_admin_action(
            admin=admin,
            action_type="ban_user",
            target_type="user",
            target_id=str(user.id),
            details={
                "duration_days": duration_days,
                "is_permanent": duration_days is None,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
            reason=reason,
        )

        # Notify user
        NotificationService.send_notification(
            user=user,
            notification_type="account_banned",
            title="Account Banned",
            message=f"Your account has been banned. Reason: {reason}",
            context={
                "reason": reason,
                "is_permanent": duration_days is None,
                "duration_days": duration_days,
            },
        )

        # Notify admin team
        admin_users = User.objects.filter(is_staff=True)
        for admin_user in admin_users:
            if admin_user != admin:
                NotificationService.send_notification(
                    user=admin_user,
                    notification_type="user_banned",
                    title="User Banned",
                    message=f"{admin.username} banned {user.username}",
                    context={
                        "user_id": str(user.id),
                        "username": user.username,
                        "reason": reason,
                        "duration_days": duration_days,
                    },
                )

        return ban

    @staticmethod
    def unban_user(admin: User, user: User, reason: str) -> None:
        """
        Unban user account.

        Args:
            admin: Admin unbanning the user
            user: User to unban
            reason: Reason for unbanning
        """
        if not admin.is_staff:
            raise PermissionDenied("Only staff can unban users")

        # Get active ban
        active_ban = user.bans.filter(is_active=True).first()
        if not active_ban:
            raise ValidationError("User is not banned")

        # Lift ban
        active_ban.is_active = False
        active_ban.lifted_at = timezone.now()
        active_ban.lifted_by = admin
        active_ban.lift_reason = reason
        active_ban.save()

        # Re-enable authentication
        user.is_active = True
        user.save()

        # Audit log
        AuditService.log_admin_action(
            admin=admin,
            action_type="unban_user",
            target_type="user",
            target_id=str(user.id),
            details={},
            reason=reason,
        )

        # Notify user
        NotificationService.send_notification(
            user=user,
            notification_type="account_unbanned",
            title="Account Unbanned",
            message=f"Your account has been unbanned. Reason: {reason}",
            context={"reason": reason},
        )

    @staticmethod
    def verify_user_phone(admin: User, user: User) -> None:
        """
        Manually verify phone (for verification issues).

        Args:
            admin: Admin verifying the phone
            user: User whose phone to verify
        """
        if not admin.is_staff:
            raise PermissionDenied("Only staff can manually verify phones")

        user.phone_verified = True
        user.save()

        # Audit log
        AuditService.log_admin_action(
            admin=admin,
            action_type="verify_phone",
            target_type="user",
            target_id=str(user.id),
            details={"phone_number": user.phone_number},
            reason="Manual phone verification",
        )

        # Notify user
        NotificationService.send_notification(
            user=user,
            notification_type="phone_verified",
            title="Phone Verified",
            message="Your phone has been manually verified by an administrator",
            context={},
        )

    @staticmethod
    def get_moderation_queue() -> dict:
        """
        Get items requiring admin review.

        Returns:
            Dictionary with flagged users and suspicious activity
        """
        # Flagged users
        flagged_users_qs = AdminFlag.objects.filter(status="pending").select_related(
            "user", "flagged_by"
        )

        flagged_users = [
            {
                "flag_id": str(flag.id),
                "user_id": str(flag.user.id),
                "username": flag.user.username,
                "reason": flag.reason,
                "flagged_by": flag.flagged_by.username if flag.flagged_by else "System",
                "flagged_at": flag.created_at.isoformat(),
                "abuse_scores": {
                    "spam": flag.confidence if flag.detection_type == "spam" else 0,
                    "multi_account": (
                        flag.confidence if flag.detection_type == "multi_account" else 0
                    ),
                },
            }
            for flag in flagged_users_qs
        ]

        # Suspicious activity (high-confidence detections not yet flagged)
        # This would be populated by abuse detection service
        suspicious_activity = []

        pending_count = len(flagged_users) + len(suspicious_activity)

        return {
            "flagged_users": flagged_users,
            "suspicious_activity": suspicious_activity,
            "pending_count": pending_count,
        }

    @staticmethod
    def resolve_flag(admin: User, flag_id: str, resolution: str, notes: str) -> None:
        """
        Resolve flagged item.

        Args:
            admin: Admin resolving the flag
            flag_id: ID of flag to resolve
            resolution: Resolution type (no_action, warned, banned)
            notes: Resolution notes
        """
        if not admin.is_staff:
            raise PermissionDenied("Only staff can resolve flags")

        try:
            flag = AdminFlag.objects.get(id=flag_id)
        except AdminFlag.DoesNotExist:
            raise ValidationError("Flag not found")

        if flag.status == "resolved":
            raise ValidationError("Flag already resolved")

        flag.status = "resolved"
        flag.resolution = resolution
        flag.resolution_notes = notes
        flag.resolved_by = admin
        flag.resolved_at = timezone.now()
        flag.save()

        # Audit log
        AuditService.log_admin_action(
            admin=admin,
            action_type="resolve_flag",
            target_type="flag",
            target_id=flag_id,
            details={
                "resolution": resolution,
                "user_id": str(flag.user.id),
                "username": flag.user.username,
            },
            reason=notes,
        )

        # Notify reporter if applicable
        if flag.flagged_by and flag.flagged_by != admin:
            NotificationService.send_notification(
                user=flag.flagged_by,
                notification_type="flag_resolved",
                title="Flag Resolved",
                message=f"Your flag on {flag.user.username} has been resolved: {resolution}",
                context={"resolution": resolution, "notes": notes},
            )
