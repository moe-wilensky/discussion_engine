"""
Firebase Cloud Messaging (FCM) service for push notifications.

Handles sending push notifications to user devices via Firebase.
"""

import logging
from typing import List, Dict, Optional

# Firebase Admin SDK will be imported when configured
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FCM_AVAILABLE = True
except ImportError:
    FCM_AVAILABLE = False
    
from django.conf import settings

from core.models import User, UserDevice

logger = logging.getLogger(__name__)


class FCMService:
    """Firebase Cloud Messaging service for push notifications."""
    
    _initialized = False
    
    @classmethod
    def initialize(cls):
        """
        Initialize Firebase Admin SDK.
        
        Should be called once at application startup.
        Reads credentials from settings.FIREBASE_CREDENTIALS_PATH.
        """
        if cls._initialized or not FCM_AVAILABLE:
            return
        
        try:
            cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
            if cred_path:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                cls._initialized = True
                logger.info("Firebase Admin SDK initialized successfully")
            else:
                logger.warning("FIREBASE_CREDENTIALS_PATH not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
    
    @staticmethod
    def send_to_device(
        fcm_token: str,
        title: str,
        body: str,
        data: Optional[Dict] = None
    ) -> bool:
        """
        Send push notification to a single device.
        
        Args:
            fcm_token: FCM device token
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not FCM_AVAILABLE or not FCMService._initialized:
            logger.warning("FCM not available or not initialized")
            return False
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=data or {},
                token=fcm_token
            )
            
            response = messaging.send(message)
            logger.info(f"Successfully sent message: {response}")
            return True
            
        except messaging.UnregisteredError:
            # Token is invalid, should deactivate device
            logger.warning(f"Invalid FCM token: {fcm_token}")
            UserDevice.objects.filter(fcm_token=fcm_token).update(is_active=False)
            return False
            
        except Exception as e:
            logger.error(f"Failed to send FCM message: {e}")
            return False
    
    @staticmethod
    def send_to_user(
        user: User,
        title: str,
        body: str,
        data: Optional[Dict] = None
    ) -> int:
        """
        Send push notification to all active devices for a user.
        
        Args:
            user: User to send notification to
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            
        Returns:
            Number of devices successfully sent to
        """
        devices = user.devices.filter(is_active=True)
        success_count = 0
        
        for device in devices:
            if FCMService.send_to_device(device.fcm_token, title, body, data):
                success_count += 1
                # Update last_used timestamp
                device.save(update_fields=['last_used'])
        
        return success_count
    
    @staticmethod
    def send_to_multiple_users(
        users: List[User],
        title: str,
        body: str,
        data: Optional[Dict] = None
    ) -> Dict[int, int]:
        """
        Send push notification to multiple users.
        
        Args:
            users: List of users to send to
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            
        Returns:
            Dictionary mapping user_id to number of devices sent to
        """
        results = {}
        
        for user in users:
            count = FCMService.send_to_user(user, title, body, data)
            results[user.id] = count
        
        return results
    
    @staticmethod
    def register_device(
        user: User,
        fcm_token: str,
        device_type: str,
        device_name: str = ""
    ) -> UserDevice:
        """
        Register a device for push notifications.
        
        Args:
            user: User who owns the device
            fcm_token: FCM registration token
            device_type: Type of device (ios/android/web)
            device_name: Optional device name
            
        Returns:
            UserDevice instance
        """
        # Check if token already exists
        device, created = UserDevice.objects.get_or_create(
            fcm_token=fcm_token,
            defaults={
                'user': user,
                'device_type': device_type,
                'device_name': device_name,
                'is_active': True
            }
        )
        
        if not created:
            # Update existing device
            device.user = user
            device.device_type = device_type
            if device_name:
                device.device_name = device_name
            device.is_active = True
            device.save()
        
        logger.info(f"Registered device for {user.username}: {device_type}")
        return device
    
    @staticmethod
    def unregister_device(fcm_token: str) -> bool:
        """
        Unregister a device (mark as inactive).
        
        Args:
            fcm_token: FCM token to unregister
            
        Returns:
            True if device was found and deactivated
        """
        updated = UserDevice.objects.filter(fcm_token=fcm_token).update(is_active=False)
        return updated > 0
