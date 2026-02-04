"""
Notification API endpoints.

Handles notification CRUD operations and user preferences.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.shortcuts import get_object_or_404
import logging

from core.models import NotificationLog, NotificationPreference
from core.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_notifications(request):
    """
    Get user's notifications.

    GET /api/notifications/?page=1&page_size=20&unread_only=false

    Response:
        {
            "count": 50,
            "next": "...",
            "previous": "...",
            "unread_count": 5,
            "notifications": [
                {
                    "id": "uuid",
                    "type": "mrp_expiring_soon",
                    "title": "Response time running out",
                    "message": "You have 15 minutes remaining...",
                    "context": {...},
                    "created_at": "2026-02-03T14:45:00Z",
                    "read": false,
                    "is_critical": true
                }
            ]
        }
    """
    unread_only = request.query_params.get("unread_only", "false").lower() == "true"

    # Get notifications
    notifications = NotificationLog.objects.filter(user=request.user)

    if unread_only:
        notifications = notifications.filter(read=False)

    # Get unread count
    unread_count = NotificationLog.objects.filter(user=request.user, read=False).count()

    # Paginate
    paginator = NotificationPagination()
    paginated_notifications = paginator.paginate_queryset(notifications, request)

    # Serialize
    notifications_data = []
    for notif in paginated_notifications:
        notifications_data.append(
            {
                "id": str(notif.id),
                "type": notif.notification_type,
                "title": notif.title,
                "message": notif.message,
                "context": notif.context,
                "created_at": notif.created_at.isoformat(),
                "read": notif.read,
                "is_critical": notif.is_critical,
            }
        )

    return paginator.get_paginated_response(
        {"unread_count": unread_count, "notifications": notifications_data}
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    """
    Mark a notification as read.

    POST /api/notifications/{notification_id}/mark-read/

    Response:
        {
            "success": true
        }
    """
    notification = get_object_or_404(
        NotificationLog, id=notification_id, user=request.user
    )

    if not notification.read:
        notification.read = True
        notification.read_at = timezone.now()
        notification.save()

    return Response({"success": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    """
    Mark all notifications as read.

    POST /api/notifications/mark-all-read/

    Response:
        {
            "success": true,
            "marked_count": 15
        }
    """
    now = timezone.now()
    marked_count = NotificationLog.objects.filter(user=request.user, read=False).update(
        read=True, read_at=now
    )

    return Response(
        {"success": True, "marked_count": marked_count}, status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_notification_preferences(request):
    """
    Get user's notification preferences.

    GET /api/notifications/preferences/

    Response:
        {
            "preferences": [
                {
                    "type": "mrp_expiring_soon",
                    "enabled": true,
                    "is_critical": true,
                    "delivery_methods": {
                        "in_app": true,
                        "email": true,
                        "push": false
                    }
                }
            ]
        }
    """
    # Ensure preferences exist for all notification types
    NotificationService.create_notification_preferences(request.user)

    # Get all preferences
    preferences = NotificationPreference.objects.filter(user=request.user)

    preferences_data = []
    for pref in preferences:
        is_critical = (
            pref.notification_type in NotificationService.CRITICAL_NOTIFICATIONS
        )

        preferences_data.append(
            {
                "type": pref.notification_type,
                "enabled": pref.enabled,
                "is_critical": is_critical,
                "delivery_methods": pref.delivery_method,
            }
        )

    return Response({"preferences": preferences_data}, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_notification_preferences(request):
    """
    Update user's notification preferences.

    PATCH /api/notifications/preferences/

    Request:
        {
            "preferences": [
                {
                    "type": "new_response_posted",
                    "enabled": true,
                    "delivery_methods": {
                        "in_app": true,
                        "email": false,
                        "push": true
                    }
                }
            ]
        }

    Response:
        {
            "success": true,
            "updated_count": 1
        }
    """
    preferences_to_update = request.data.get("preferences", [])

    if not isinstance(preferences_to_update, list):
        return Response(
            {"error": "preferences must be a list"}, status=status.HTTP_400_BAD_REQUEST
        )

    updated_count = 0

    for pref_data in preferences_to_update:
        notification_type = pref_data.get("type")
        if not notification_type:
            continue

        # Check if notification type is valid
        if notification_type not in NotificationService.ALL_NOTIFICATION_TYPES:
            continue

        # Get or create preference
        preference, created = NotificationPreference.objects.get_or_create(
            user=request.user,
            notification_type=notification_type,
            defaults={
                "enabled": True,
                "delivery_method": {"in_app": True, "email": False, "push": False},
            },
        )

        # Update enabled status (only for optional notifications)
        if notification_type not in NotificationService.CRITICAL_NOTIFICATIONS:
            if "enabled" in pref_data:
                preference.enabled = pref_data["enabled"]

        # Update delivery methods
        if "delivery_methods" in pref_data:
            new_delivery = pref_data["delivery_methods"]

            # For critical notifications, in_app is always True
            if notification_type in NotificationService.CRITICAL_NOTIFICATIONS:
                new_delivery["in_app"] = True

            preference.delivery_method = new_delivery

        preference.save()
        updated_count += 1

    return Response(
        {"success": True, "updated_count": updated_count}, status=status.HTTP_200_OK
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_notification(request, notification_id):
    """
    Delete a notification.

    DELETE /api/notifications/{notification_id}/

    Response:
        {
            "success": true
        }
    """
    notification = get_object_or_404(
        NotificationLog, id=notification_id, user=request.user
    )

    notification.delete()

    return Response({"success": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def register_device(request):
    """
    Register a device for push notifications.
    
    POST /api/notifications/devices/register/
    {
        "fcm_token": "firebase_token_here",
        "device_type": "ios",  // or "android", "web"
        "device_name": "John's iPhone"  // optional
    }
    
    Response:
        {
            "success": true,
            "device_id": "uuid",
            "message": "Device registered successfully"
        }
    """
    from core.services.fcm_service import FCMService
    
    fcm_token = request.data.get("fcm_token")
    device_type = request.data.get("device_type")
    device_name = request.data.get("device_name", "")
    
    if not fcm_token or not device_type:
        return Response(
            {"error": "fcm_token and device_type are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if device_type not in ["ios", "android", "web"]:
        return Response(
            {"error": "device_type must be ios, android, or web"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        device = FCMService.register_device(
            user=request.user,
            fcm_token=fcm_token,
            device_type=device_type,
            device_name=device_name
        )
        
        return Response({
            "success": True,
            "device_id": str(device.id),
            "message": "Device registered successfully"
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Failed to register device: {e}")
        return Response(
            {"error": "Failed to register device"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unregister_device(request):
    """
    Unregister a device from push notifications.
    
    POST /api/notifications/devices/unregister/
    {
        "fcm_token": "firebase_token_here"
    }
    
    Response:
        {
            "success": true,
            "message": "Device unregistered successfully"
        }
    """
    from core.services.fcm_service import FCMService
    
    fcm_token = request.data.get("fcm_token")
    
    if not fcm_token:
        return Response(
            {"error": "fcm_token is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    success = FCMService.unregister_device(fcm_token)
    
    if success:
        return Response({
            "success": True,
            "message": "Device unregistered successfully"
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": "Device not found"
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_devices(request):
    """
    List user's registered devices.
    
    GET /api/notifications/devices/
    
    Response:
        {
            "devices": [
                {
                    "id": "uuid",
                    "device_type": "ios",
                    "device_name": "John's iPhone",
                    "is_active": true,
                    "last_used": "2026-02-03T14:45:00Z",
                    "created_at": "2026-01-01T10:00:00Z"
                }
            ]
        }
    """
    devices = request.user.devices.filter(is_active=True)
    
    device_list = [
        {
            "id": str(device.id),
            "device_type": device.device_type,
            "device_name": device.device_name,
            "is_active": device.is_active,
            "last_used": device.last_used.isoformat(),
            "created_at": device.created_at.isoformat(),
        }
        for device in devices
    ]
    
    return Response({"devices": device_list}, status=status.HTTP_200_OK)

