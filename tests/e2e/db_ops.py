"""
Async-safe database operations for E2E tests.

This module provides async wrappers around Django ORM operations to prevent
SynchronousOnlyOperation errors when using pytest-asyncio with Playwright.

All database operations should use sync_to_async with thread_sensitive=True
to ensure proper database connection handling in async contexts.
"""

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from core.models import (
    Discussion,
    DiscussionParticipant,
    Round,
    Response,
    Vote,
    Invite,
    PlatformConfig,
)

User = get_user_model()


# User Operations
@sync_to_async(thread_sensitive=True)
def create_user(username, password="testpass123", **kwargs):
    """Create a user asynchronously."""
    user = User.objects.create_user(
        username=username,
        password=password,
        **kwargs
    )
    return user


@sync_to_async(thread_sensitive=True)
def create_verified_user(username, **kwargs):
    """Create a verified user ready for testing."""
    defaults = {
        "phone_verified": True,
        "platform_invites_banked": 5,
        "discussion_invites_banked": 10,
    }
    defaults.update(kwargs)
    
    # Generate unique phone number if not provided
    if "phone_number" not in defaults:
        import random
        defaults["phone_number"] = f"+1555{random.randint(1000000, 9999999)}"
    
    user = User.objects.create_user(
        username=username,
        password="testpass123",
        **defaults
    )
    return user


@sync_to_async(thread_sensitive=True)
def get_user(username):
    """Get user by username."""
    return User.objects.get(username=username)


# Discussion Operations
@sync_to_async(thread_sensitive=True)
def create_discussion(initiator, topic_headline, topic_details="", **kwargs):
    """Create a discussion asynchronously."""
    defaults = {
        "max_response_length_chars": 1000,
        "min_response_time_minutes": 5,
        "response_time_multiplier": 1.0,
        "status": "active",
    }
    defaults.update(kwargs)
    
    discussion = Discussion.objects.create(
        initiator=initiator,
        topic_headline=topic_headline,
        topic_details=topic_details,
        **defaults
    )
    return discussion


@sync_to_async(thread_sensitive=True)
def get_discussion(discussion_id):
    """Get discussion by ID."""
    return Discussion.objects.get(id=discussion_id)


@sync_to_async(thread_sensitive=True)
def get_discussion_by_topic(topic_headline):
    """Get discussion by topic headline."""
    return Discussion.objects.filter(topic_headline=topic_headline).first()


@sync_to_async(thread_sensitive=True)
def refresh_discussion(discussion):
    """Refresh discussion from database."""
    discussion.refresh_from_db()
    return discussion


# Participant Operations
@sync_to_async(thread_sensitive=True)
def create_participant(discussion, user, role="active"):
    """Create a discussion participant asynchronously."""
    return DiscussionParticipant.objects.create(
        discussion=discussion,
        user=user,
        role=role
    )


@sync_to_async(thread_sensitive=True)
def get_participant(discussion, user):
    """Get participant by discussion and user."""
    return DiscussionParticipant.objects.filter(
        discussion=discussion,
        user=user
    ).first()


# Round Operations
@sync_to_async(thread_sensitive=True)
def create_round(discussion, round_number, status="in_progress", **kwargs):
    """Create a round asynchronously."""
    return Round.objects.create(
        discussion=discussion,
        round_number=round_number,
        status=status,
        **kwargs
    )


@sync_to_async(thread_sensitive=True)
def get_round(discussion, round_number):
    """Get round by discussion and round number."""
    return Round.objects.filter(
        discussion=discussion,
        round_number=round_number
    ).first()


@sync_to_async(thread_sensitive=True)
def update_round_status(round_obj, status, **kwargs):
    """Update round status and other fields."""
    round_obj.status = status
    for key, value in kwargs.items():
        setattr(round_obj, key, value)
    round_obj.save()
    return round_obj


@sync_to_async(thread_sensitive=True)
def refresh_round(round_obj):
    """Refresh round from database."""
    round_obj.refresh_from_db()
    return round_obj


# Response Operations
@sync_to_async(thread_sensitive=True)
def create_response(user, round_obj, content, **kwargs):
    """Create a response asynchronously."""
    defaults = {
        "character_count": len(content),
    }
    defaults.update(kwargs)
    
    return Response.objects.create(
        user=user,
        round=round_obj,
        content=content,
        **defaults
    )


@sync_to_async(thread_sensitive=True)
def get_response(user, round_obj):
    """Get response by user and round."""
    return Response.objects.filter(
        user=user,
        round=round_obj
    ).first()


@sync_to_async(thread_sensitive=True)
def get_response_by_content(round_obj, content):
    """Get response by content."""
    return Response.objects.filter(
        round=round_obj,
        content=content
    ).first()


@sync_to_async(thread_sensitive=True)
def count_responses(round_obj):
    """Count responses in a round."""
    return Response.objects.filter(round=round_obj).count()


# Vote Operations
@sync_to_async(thread_sensitive=True)
def create_vote(user, round_obj, **kwargs):
    """Create a vote asynchronously."""
    defaults = {
        "mrl_vote": "no_change",
        "rtm_vote": "no_change",
    }
    defaults.update(kwargs)
    
    return Vote.objects.create(
        user=user,
        round=round_obj,
        **defaults
    )


@sync_to_async(thread_sensitive=True)
def get_vote(user, round_obj):
    """Get vote by user and round."""
    return Vote.objects.filter(
        user=user,
        round=round_obj
    ).first()


# Platform Config Operations
@sync_to_async(thread_sensitive=True)
def get_platform_config():
    """Get or create platform config."""
    return PlatformConfig.load()


# Invite Operations
@sync_to_async(thread_sensitive=True)
def create_invite(inviter, invite_type="platform", status="sent", **kwargs):
    """Create an invite asynchronously."""
    defaults = {
        "code": Invite.generate_code(),
    }
    defaults.update(kwargs)

    return Invite.objects.create(
        inviter=inviter,
        invite_type=invite_type,
        status=status,
        **defaults
    )


@sync_to_async(thread_sensitive=True)
def get_invite_by_code(code):
    """Get invite by code."""
    return Invite.objects.filter(code=code).first()


@sync_to_async(thread_sensitive=True)
def refresh_invite(invite):
    """Refresh invite from database."""
    invite.refresh_from_db()
    return invite


@sync_to_async(thread_sensitive=True)
def get_user_by_phone(phone_number):
    """Get user by phone number."""
    return User.objects.filter(phone_number=phone_number).first()


@sync_to_async(thread_sensitive=True)
def refresh_user(user):
    """Refresh user from database."""
    user.refresh_from_db()
    return user


# Generic Query Operations
@sync_to_async(thread_sensitive=True)
def exists(queryset):
    """Check if queryset has any results."""
    return queryset.exists()


@sync_to_async(thread_sensitive=True)
def count(queryset):
    """Count queryset results."""
    return queryset.count()


@sync_to_async(thread_sensitive=True)
def first(queryset):
    """Get first result from queryset."""
    return queryset.first()


@sync_to_async(thread_sensitive=True)
def all_list(queryset):
    """Convert queryset to list."""
    return list(queryset.all())
