"""
Admin API endpoints.

Provides REST API for admin dashboard, platform configuration,
user management, and moderation queue.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response as APIResponse

from core.models import User, PlatformConfig
from core.services.admin_service import AdminService


class IsAdminUser(BasePermission):
    """Only admin users can access."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class IsSuperAdminUser(BasePermission):
    """Only superadmin users can access (for config changes)."""

    def has_permission(self, request, view):
        return (
            request.user and request.user.is_authenticated and request.user.is_superuser
        )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_platform_config(request):
    """
    Get platform configuration.

    GET /api/admin/platform-config/
    """
    config = PlatformConfig.load()

    return APIResponse(
        {
            "config": {
                "new_user_platform_invites": config.new_user_platform_invites,
                "new_user_discussion_invites": config.new_user_discussion_invites,
                "responses_to_unlock_invites": config.responses_to_unlock_invites,
                "responses_per_platform_invite": config.responses_per_platform_invite,
                "responses_per_discussion_invite": config.responses_per_discussion_invite,
                "max_discussion_participants": config.max_discussion_participants,
                "n_responses_before_mrp": config.n_responses_before_mrp,
                "max_headline_length": config.max_headline_length,
                "max_topic_length": config.max_topic_length,
                "voting_increment_percentage": config.voting_increment_percentage,
                "vote_based_removal_threshold": config.vote_based_removal_threshold,
                "max_discussion_duration_days": config.max_discussion_duration_days,
                "max_discussion_rounds": config.max_discussion_rounds,
                "max_discussion_responses": config.max_discussion_responses,
                "round_1_phase_1_timeout_days": config.round_1_phase_1_timeout_days,
                "response_edit_percentage": config.response_edit_percentage,
                "response_edit_limit": config.response_edit_limit,
            },
            "last_updated": config.updated_at.isoformat(),
        }
    )


@api_view(["PATCH"])
@permission_classes([IsSuperAdminUser])
def update_platform_config(request):
    """
    Update platform configuration.

    PATCH /api/admin/platform-config/
    """
    try:
        old_config = PlatformConfig.load()
        old_values = {
            field: getattr(old_config, field) for field in request.data.keys()
        }

        updated_config = AdminService.update_platform_config(
            admin=request.user, updates=request.data
        )

        # Build changes list
        changes = []
        for field, new_value in request.data.items():
            if field in old_values:
                changes.append(
                    {"field": field, "old": old_values[field], "new": new_value}
                )

        return APIResponse(
            {
                "updated": True,
                "config": {
                    field: getattr(updated_config, field)
                    for field in request.data.keys()
                },
                "changes": changes,
            }
        )

    except Exception as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_platform_analytics(request):
    """
    Get platform analytics.

    GET /api/admin/analytics/
    """
    analytics = AdminService.get_platform_analytics()
    return APIResponse(analytics)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_user_analytics(request, user_id):
    """
    Get user analytics.

    GET /api/admin/users/{user_id}/analytics/
    """
    try:
        user = User.objects.get(id=user_id)
        analytics = AdminService.get_user_analytics(user)
        return APIResponse(analytics)

    except User.DoesNotExist:
        return APIResponse(
            {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def flag_user(request, user_id):
    """
    Flag user for review.

    POST /api/admin/users/{user_id}/flag/
    """
    try:
        user = User.objects.get(id=user_id)

        reason = request.data.get("reason", "")
        notes = request.data.get("notes", "")

        if not reason:
            return APIResponse(
                {"error": "Reason is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        flag = AdminService.flag_user(
            admin=request.user, user=user, reason=f"{reason}. {notes}".strip()
        )

        return APIResponse({"flag_id": str(flag.id), "flagged": True})

    except User.DoesNotExist:
        return APIResponse(
            {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def ban_user(request, user_id):
    """
    Ban user account.

    POST /api/admin/users/{user_id}/ban/
    """
    try:
        user = User.objects.get(id=user_id)

        reason = request.data.get("reason", "")
        duration_days = request.data.get("duration_days")

        if not reason:
            return APIResponse(
                {"error": "Reason is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        ban = AdminService.ban_user(
            admin=request.user, user=user, reason=reason, duration_days=duration_days
        )

        return APIResponse({"banned": True, "permanent": ban.is_permanent})

    except User.DoesNotExist:
        return APIResponse(
            {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def unban_user(request, user_id):
    """
    Unban user account.

    POST /api/admin/users/{user_id}/unban/
    """
    try:
        user = User.objects.get(id=user_id)

        reason = request.data.get("reason", "")

        if not reason:
            return APIResponse(
                {"error": "Reason is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        AdminService.unban_user(admin=request.user, user=user, reason=reason)

        return APIResponse({"unbanned": True})

    except User.DoesNotExist:
        return APIResponse(
            {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def verify_user_phone(request, user_id):
    """
    Manually verify user phone.

    POST /api/admin/users/{user_id}/verify-phone/
    """
    try:
        user = User.objects.get(id=user_id)

        AdminService.verify_user_phone(admin=request.user, user=user)

        return APIResponse({"verified": True})

    except User.DoesNotExist:
        return APIResponse(
            {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_moderation_queue(request):
    """
    Get moderation queue.

    GET /api/admin/moderation-queue/
    """
    queue = AdminService.get_moderation_queue()
    return APIResponse(queue)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def resolve_flag(request, flag_id):
    """
    Resolve flagged item.

    POST /api/admin/moderation-queue/{flag_id}/resolve/
    """
    try:
        resolution = request.data.get("resolution", "")
        notes = request.data.get("notes", "")

        if not resolution:
            return APIResponse(
                {"error": "Resolution is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        AdminService.resolve_flag(
            admin=request.user, flag_id=flag_id, resolution=resolution, notes=notes
        )

        return APIResponse({"resolved": True})

    except Exception as e:
        return APIResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
