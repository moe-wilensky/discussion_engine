"""
Audit logging service for admin actions.

Provides comprehensive tracking of all administrative operations
for compliance, investigation, and accountability.
"""

from typing import List, Optional
from datetime import datetime

from django.utils import timezone

from core.models import AuditLog, User


class AuditService:
    """Audit logging for admin actions."""

    @staticmethod
    def log_admin_action(
        admin: User,
        action_type: str,
        target_type: str,
        target_id: str,
        details: dict,
        reason: str = "",
    ) -> AuditLog:
        """
        Log admin action.

        Args:
            admin: Admin user performing action
            action_type: Type of action (ban_user, update_config, etc.)
            target_type: Type of target (user, discussion, config, etc.)
            target_id: ID of target
            details: Additional details about the action
            reason: Reason for action

        Returns:
            Created AuditLog instance
        """
        audit_log = AuditLog.objects.create(
            admin=admin,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            details=details,
            reason=reason,
        )

        return audit_log

    @staticmethod
    def get_audit_trail(
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        admin: Optional[User] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[dict]:
        """
        Query audit logs with filters.

        Args:
            target_type: Filter by target type
            target_id: Filter by target ID
            admin: Filter by admin user
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            List of audit log dictionaries
        """
        queryset = AuditLog.objects.all()

        if target_type:
            queryset = queryset.filter(target_type=target_type)

        if target_id:
            queryset = queryset.filter(target_id=target_id)

        if admin:
            queryset = queryset.filter(admin=admin)

        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)

        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        return [
            {
                "id": str(log.id),
                "admin": log.admin.username if log.admin else "System",
                "action_type": log.action_type,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": log.details,
                "reason": log.reason,
                "created_at": log.created_at.isoformat(),
            }
            for log in queryset[:100]  # Limit to 100 most recent
        ]
