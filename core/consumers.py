"""
WebSocket consumer for real-time discussion updates.

Handles real-time updates for:
- New responses
- MRP recalculation
- Round status changes
- MRP expiration warnings
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class DiscussionConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for discussion updates.

    Clients connect to: ws://host/ws/discussions/{discussion_id}/
    """

    async def connect(self):
        """Handle WebSocket connection."""
        self.discussion_id = self.scope["url_route"]["kwargs"]["discussion_id"]
        self.room_group_name = f"discussion_{self.discussion_id}"
        self.user = self.scope.get("user")

        # Check authentication
        if not self.user or not self.user.is_authenticated:
            logger.warning(
                f"Unauthorized WebSocket connection attempt to discussion {self.discussion_id}"
            )
            await self.close(code=4001)
            return

        # Check if user is a participant in the discussion
        has_access = await self.check_discussion_access()
        if not has_access:
            logger.warning(
                f"User {self.user.id} attempted to connect to discussion {self.discussion_id} without participant access"
            )
            await self.close(code=4003)
            return

        # Join discussion channel
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()

    @database_sync_to_async
    def check_discussion_access(self):
        """
        Check if the user is a participant in the discussion.

        Returns:
            bool: True if user is a participant, False otherwise
        """
        from core.models import Discussion

        try:
            discussion = Discussion.objects.get(id=self.discussion_id)
            return discussion.participants.filter(user=self.user).exists()
        except Discussion.DoesNotExist:
            return False

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave discussion channel
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Receive message from WebSocket.

        Not used for this consumer - clients only receive updates.
        """
        pass

    async def new_response(self, event):
        """
        Broadcast new response notification.

        Event structure:
        {
            'type': 'new_response',
            'response_id': <id>,
            'author': <username>,
            'round_number': <number>,
            'response_number': <number>,
            'mrp_updated': <bool>,
            'new_mrp_minutes': <float>,
            'new_mrp_deadline': <iso_datetime>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "new_response",
                    "response_id": event["response_id"],
                    "author": event["author"],
                    "round_number": event["round_number"],
                    "response_number": event["response_number"],
                    "mrp_updated": event.get("mrp_updated", False),
                    "new_mrp_minutes": event.get("new_mrp_minutes"),
                    "new_mrp_deadline": event.get("new_mrp_deadline"),
                }
            )
        )

    async def mrp_timer_update(self, event):
        """
        Broadcast MRP timer countdown update.

        Event structure:
        {
            'type': 'mrp_timer_update',
            'round_number': <number>,
            'time_remaining_seconds': <int>,
            'mrp_deadline': <iso_datetime>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "mrp_timer_update",
                    "round_number": event["round_number"],
                    "time_remaining_seconds": event["time_remaining_seconds"],
                    "mrp_deadline": event["mrp_deadline"],
                }
            )
        )

    async def mrp_warning(self, event):
        """
        Broadcast MRP expiration warning.

        Event structure:
        {
            'type': 'mrp_warning',
            'round_number': <number>,
            'percentage_remaining': <percentage>,
            'time_remaining_minutes': <float>,
            'mrp_deadline': <iso_datetime>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "mrp_warning",
                    "round_number": event["round_number"],
                    "percentage_remaining": event["percentage_remaining"],
                    "time_remaining_minutes": event["time_remaining_minutes"],
                    "mrp_deadline": event["mrp_deadline"],
                }
            )
        )

    async def round_ended(self, event):
        """
        Broadcast round ended notification.

        Event structure:
        {
            'type': 'round_ended',
            'round_number': <number>,
            'reason': <string>,
            'voting_starts': <iso_datetime>,
            'voting_ends': <iso_datetime>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "round_ended",
                    "round_number": event["round_number"],
                    "reason": event.get("reason", "all_responded"),
                    "voting_starts": event.get("voting_starts"),
                    "voting_ends": event.get("voting_ends"),
                }
            )
        )

    async def mrp_expired(self, event):
        """
        Broadcast MRP expiration notification.

        Event structure:
        {
            'type': 'mrp_expired',
            'round_number': <number>,
            'observers_added': [<user_ids>]
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "mrp_expired",
                    "round_number": event["round_number"],
                    "observers_added": event.get("observers_added", []),
                }
            )
        )

    async def discussion_archived(self, event):
        """
        Broadcast discussion archived notification.

        Event structure:
        {
            'type': 'discussion_archived',
            'reason': <string>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "discussion_archived",
                    "reason": event.get("reason", "unknown"),
                }
            )
        )

    async def voting_started(self, event):
        """
        Broadcast voting window opened notification.

        Event structure:
        {
            'type': 'voting_started',
            'round_number': <number>,
            'voting_closes_at': <iso_datetime>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "voting_started",
                    "round_number": event["round_number"],
                    "voting_closes_at": event.get("voting_closes_at"),
                }
            )
        )

    async def voting_updated(self, event):
        """
        Broadcast voting update notification.

        Event structure:
        {
            'type': 'voting_updated',
            'round_number': <number>,
            'parameter': 'mrl' or 'rtm' or 'removal',
            'votes_cast': <count>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "voting_updated",
                    "round_number": event["round_number"],
                    "parameter": event.get("parameter"),
                    "votes_cast": event.get("votes_cast"),
                }
            )
        )

    async def voting_closed(self, event):
        """
        Broadcast voting window closed notification.

        Event structure:
        {
            'type': 'voting_closed',
            'round_number': <number>,
            'mrl_result': <string>,
            'rtm_result': <string>,
            'users_removed': [<user_ids>]
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "voting_closed",
                    "round_number": event["round_number"],
                    "mrl_result": event.get("mrl_result"),
                    "rtm_result": event.get("rtm_result"),
                    "users_removed": event.get("users_removed", []),
                }
            )
        )

    async def parameter_changed(self, event):
        """
        Broadcast parameter change notification.

        Event structure:
        {
            'type': 'parameter_changed',
            'parameter': 'mrl' or 'rtm',
            'old_value': <value>,
            'new_value': <value>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "parameter_changed",
                    "parameter": event["parameter"],
                    "old_value": event.get("old_value"),
                    "new_value": event.get("new_value"),
                }
            )
        )

    async def user_removed(self, event):
        """
        Broadcast user removal notification.

        Event structure:
        {
            'type': 'user_removed',
            'user_id': <id>,
            'username': <string>,
            'reason': 'vote_based_removal'
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_removed",
                    "user_id": event["user_id"],
                    "username": event.get("username"),
                    "reason": event.get("reason"),
                }
            )
        )

    async def next_round_started(self, event):
        """
        Broadcast next round started notification.

        Event structure:
        {
            'type': 'next_round_started',
            'round_number': <number>,
            'discussion_id': <id>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "next_round_started",
                    "round_number": event["round_number"],
                    "discussion_id": event["discussion_id"],
                }
            )
        )


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.

    Clients connect to: ws://host/ws/notifications/
    """

    async def connect(self):
        """Handle WebSocket connection."""
        # Get user from scope (requires auth middleware)
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Subscribe to user's notification channel
        self.user_channel = f"notifications_{self.user.id}"

        await self.channel_layer.group_add(self.user_channel, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, "user_channel"):
            await self.channel_layer.group_discard(self.user_channel, self.channel_name)

    async def receive(self, text_data):
        """
        Receive message from WebSocket.

        Not used for this consumer - clients only receive notifications.
        """
        pass

    async def notification_message(self, event):
        """
        Send notification to WebSocket.

        Event structure:
        {
            'type': 'notification_message',
            'notification_id': <id>,
            'notification_type': <type>,
            'title': <title>,
            'message': <message>,
            'context': <dict>,
            'is_critical': <bool>,
            'created_at': <iso_datetime>
        }
        """
        await self.send(
            text_data=json.dumps(
                {
                    "type": "notification",
                    "notification_id": event["notification_id"],
                    "notification_type": event["notification_type"],
                    "title": event["title"],
                    "message": event["message"],
                    "context": event.get("context", {}),
                    "is_critical": event.get("is_critical", False),
                    "created_at": event.get("created_at"),
                }
            )
        )
