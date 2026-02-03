"""
Core models for the Discussion Engine platform.

This module contains all database models for managing discussions, participants,
responses, voting, moderation, and platform configuration.
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from typing import List, Optional, Tuple
import statistics


class User(AbstractUser):
    """
    Extended User model with invite tracking and platform permissions.

    Tracks both platform invites (for new users) and discussion invites
    (for adding users to specific discussions).
    """

    phone_number = models.CharField(max_length=20, unique=True)

    # Platform invite tracking
    platform_invites_acquired = models.IntegerField(default=0)
    platform_invites_used = models.IntegerField(default=0)
    platform_invites_banked = models.IntegerField(default=0)

    # Discussion invite tracking
    discussion_invites_acquired = models.IntegerField(default=0)
    discussion_invites_used = models.IntegerField(default=0)
    discussion_invites_banked = models.IntegerField(default=0)

    # Permissions and preferences
    is_platform_admin = models.BooleanField(default=False)
    behavioral_flags = models.JSONField(default=dict, blank=True)
    account_deletion_preference = models.CharField(
        max_length=20,
        choices=[
            ("delete_all", "Delete All"),
            ("preserve_data", "Preserve Data"),
        ],
        default="preserve_data",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["phone_number"]),
            models.Index(fields=["created_at"]),
        ]

    def can_send_platform_invite(self) -> bool:
        """Check if user has available platform invites."""
        return self.platform_invites_banked > 0

    def can_send_discussion_invite(self) -> bool:
        """Check if user has available discussion invites."""
        return self.discussion_invites_banked > 0

    def earn_invite(self, invite_type: str) -> None:
        """
        Award an invite to the user.

        Args:
            invite_type: Either 'platform' or 'discussion'
        """
        if invite_type == "platform":
            self.platform_invites_acquired += 1
            self.platform_invites_banked += 1
        elif invite_type == "discussion":
            self.discussion_invites_acquired += 1
            self.discussion_invites_banked += 1
        else:
            raise ValueError(f"Invalid invite_type: {invite_type}")
        self.save()

    def consume_invite(self, invite_type: str) -> None:
        """
        Consume an invite from the user's bank.

        Args:
            invite_type: Either 'platform' or 'discussion'

        Raises:
            ValidationError: If user has no invites available
        """
        if invite_type == "platform":
            if self.platform_invites_banked <= 0:
                raise ValidationError("No platform invites available")
            self.platform_invites_used += 1
            self.platform_invites_banked -= 1
        elif invite_type == "discussion":
            if self.discussion_invites_banked <= 0:
                raise ValidationError("No discussion invites available")
            self.discussion_invites_used += 1
            self.discussion_invites_banked -= 1
        else:
            raise ValueError(f"Invalid invite_type: {invite_type}")
        self.save()

    def __str__(self):
        return f"{self.username} ({self.phone_number})"


class PlatformConfig(models.Model):
    """
    Singleton model for platform-wide configuration.

    Contains all configurable parameters that control discussion behavior,
    invite mechanics, and platform limits.
    """

    # Invite configuration
    new_user_platform_invites = models.IntegerField(default=3)
    new_user_discussion_invites = models.IntegerField(default=5)
    responses_to_unlock_invites = models.IntegerField(default=3)
    responses_per_platform_invite = models.IntegerField(default=10)
    responses_per_discussion_invite = models.IntegerField(default=5)

    # Discussion limits
    max_discussion_participants = models.IntegerField(default=10)
    n_responses_before_mrp = models.IntegerField(default=2)
    max_headline_length = models.IntegerField(default=100)
    max_topic_length = models.IntegerField(default=500)

    # Invite mechanics
    invite_consumption_trigger = models.CharField(
        max_length=20,
        choices=[
            ("sent", "Sent"),
            ("accepted", "Accepted"),
        ],
        default="accepted",
    )

    # MRP calculation
    mrp_calculation_scope = models.CharField(
        max_length=20,
        choices=[
            ("current_round", "Current Round"),
            ("last_X_rounds", "Last X Rounds"),
            ("all_rounds", "All Rounds"),
        ],
        default="current_round",
    )
    mrp_calculation_x_rounds = models.IntegerField(default=3)

    # Voting configuration
    voting_increment_percentage = models.IntegerField(default=20)
    vote_based_removal_threshold = models.FloatField(default=0.5)

    # Discussion termination
    max_discussion_duration_days = models.IntegerField(default=90)
    max_discussion_rounds = models.IntegerField(default=50)
    max_discussion_responses = models.IntegerField(default=500)

    # Round timing
    round_1_phase_1_timeout_days = models.IntegerField(default=7)

    # Discussion settings
    allow_duplicate_discussions = models.BooleanField(default=False)

    # Response editing
    response_edit_percentage = models.IntegerField(default=20)
    response_edit_limit = models.IntegerField(default=2)

    # Response parameters (RTM, MRM, MRL)
    rtm_min = models.FloatField(default=0.5)
    rtm_max = models.FloatField(default=2.0)

    mrm_min_minutes = models.IntegerField(default=5)
    mrm_max_minutes = models.IntegerField(default=1440)

    mrl_min_chars = models.IntegerField(default=100)
    mrl_max_chars = models.IntegerField(default=5000)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_config"
        verbose_name = "Platform Configuration"
        verbose_name_plural = "Platform Configuration"

    def save(self, *args, **kwargs):
        """Ensure only one instance exists (singleton)."""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton instance."""
        pass

    @classmethod
    def load(cls):
        """Load or create the singleton instance."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Platform Configuration"


class Discussion(models.Model):
    """
    Represents a discussion topic and its parameters.

    Each discussion has configurable response parameters (MRL, RTM, MRM) and
    tracks its lifecycle from creation to archival.
    """

    topic_headline = models.CharField(max_length=100)
    topic_details = models.TextField(max_length=500)

    # Response parameters
    max_response_length_chars = models.IntegerField()  # MRL
    response_time_multiplier = models.FloatField()  # RTM
    min_response_time_minutes = models.IntegerField()  # MRM

    # Discussion state
    status = models.CharField(
        max_length=20,
        choices=[
            ("active", "Active"),
            ("archived", "Archived"),
        ],
        default="active",
    )

    # Relationships
    initiator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="initiated_discussions"
    )
    delegated_approver = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="delegated_discussions"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "discussions"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["initiator"]),
        ]

    def is_at_participant_cap(self) -> bool:
        """Check if discussion has reached maximum participants."""
        config = PlatformConfig.load()
        active_count = self.participants.filter(role__in=["initiator", "active"]).count()
        return active_count >= config.max_discussion_participants

    def get_active_participants(self):
        """Get all active participants (excluding observers)."""
        return self.participants.filter(role__in=["initiator", "active"])

    def should_archive(self) -> Tuple[bool, Optional[str]]:
        """
        Determine if discussion should be archived.

        Returns:
            Tuple of (should_archive: bool, reason: str or None)
        """
        config = PlatformConfig.load()

        # Check duration
        age = timezone.now() - self.created_at
        if age.days >= config.max_discussion_duration_days:
            return True, f"Exceeded maximum duration of {config.max_discussion_duration_days} days"

        # Check round count
        round_count = self.rounds.count()
        if round_count >= config.max_discussion_rounds:
            return True, f"Exceeded maximum rounds of {config.max_discussion_rounds}"

        # Check response count
        response_count = Response.objects.filter(round__discussion=self).count()
        if response_count >= config.max_discussion_responses:
            return True, f"Exceeded maximum responses of {config.max_discussion_responses}"

        return False, None

    def __str__(self):
        return f"{self.topic_headline} (by {self.initiator.username})"


class DiscussionParticipant(models.Model):
    """
    Tracks user participation in a discussion.

    Manages participant roles, observer status, and removal tracking.
    """

    discussion = models.ForeignKey(
        Discussion, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="participations")

    role = models.CharField(
        max_length=30,
        choices=[
            ("initiator", "Initiator"),
            ("active", "Active"),
            ("temporary_observer", "Temporary Observer"),
            ("permanent_observer", "Permanent Observer"),
        ],
        default="active",
    )

    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    observer_since = models.DateTimeField(null=True, blank=True)

    # Observer tracking
    observer_reason = models.CharField(
        max_length=30,
        choices=[
            ("mrp_expired", "MRP Expired"),
            ("mutual_removal", "Mutual Removal"),
            ("vote_based_removal", "Vote Based Removal"),
        ],
        null=True,
        blank=True,
    )
    posted_in_round_when_removed = models.BooleanField(default=False)
    removal_count = models.IntegerField(default=0)

    # Permissions
    can_invite_others = models.BooleanField(default=True)

    class Meta:
        db_table = "discussion_participants"
        unique_together = [["discussion", "user"]]
        indexes = [
            models.Index(fields=["discussion", "user"]),
            models.Index(fields=["user", "role"]),
            models.Index(fields=["observer_since", "observer_reason"]),
        ]

    def can_rejoin(self) -> bool:
        """
        Check if a temporary observer can rejoin as active participant.

        Returns:
            True if user can rejoin, False otherwise
        """
        if self.role != "temporary_observer":
            return False

        if self.observer_reason == "mrp_expired":
            # Can rejoin immediately if posted in removal round
            if self.posted_in_round_when_removed:
                return True
            # Otherwise must wait until next round
            # Get the latest in-progress round
            current_round = (
                self.discussion.rounds.filter(status="in_progress")
                .order_by("-round_number")
                .first()
            )
            if current_round and self.observer_since:
                # Find the round when removal occurred (round where observer_since falls)
                removal_round = (
                    self.discussion.rounds.filter(start_time__lte=self.observer_since)
                    .order_by("-start_time")
                    .first()
                )
                # Can rejoin if we're in a later round
                if removal_round and current_round.round_number > removal_round.round_number:
                    return True

        elif self.observer_reason == "mutual_removal":
            # Wait period based on removal count
            if not self.observer_since:
                return False

            wait_periods = {
                1: timedelta(hours=24),
                2: timedelta(days=7),
            }
            # Third removal and beyond = effectively permanent (365 days)
            wait_period = wait_periods.get(self.removal_count, timedelta(days=365))

            # For third removal (count >= 3), never allow rejoin
            if self.removal_count >= 3:
                return False

            if timezone.now() >= self.observer_since + wait_period:
                return True

        elif self.observer_reason == "vote_based_removal":
            # Permanent removal via vote
            return False

        return False

    def get_wait_period_end(self) -> Optional[timezone.datetime]:
        """
        Calculate when a temporary observer can rejoin.

        Returns:
            Datetime when user can rejoin, or None if not applicable
        """
        if self.role != "temporary_observer" or not self.observer_since:
            return None

        if self.observer_reason == "mrp_expired":
            if self.posted_in_round_when_removed:
                return self.observer_since  # Can rejoin immediately
            # Return start of next round (approximation)
            return self.observer_since + timedelta(hours=24)

        elif self.observer_reason == "mutual_removal":
            wait_periods = {
                1: timedelta(hours=24),
                2: timedelta(days=7),
            }
            wait_period = wait_periods.get(self.removal_count, timedelta(days=365))
            return self.observer_since + wait_period

        return None

    def __str__(self):
        return f"{self.user.username} in {self.discussion.topic_headline} ({self.role})"


class Round(models.Model):
    """
    Represents a round of responses in a discussion.

    Tracks round progression, MRP calculation, and voting phases.
    """

    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name="rounds")
    round_number = models.IntegerField()

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    final_mrp_minutes = models.FloatField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("in_progress", "In Progress"),
            ("voting", "Voting"),
            ("completed", "Completed"),
        ],
        default="in_progress",
    )

    class Meta:
        db_table = "rounds"
        unique_together = [["discussion", "round_number"]]
        indexes = [
            models.Index(fields=["discussion", "round_number"]),
            models.Index(fields=["status"]),
        ]

    def calculate_mrp(self, config: PlatformConfig) -> float:
        """
        Calculate the Median Response Period (MRP) for this round.

        Args:
            config: PlatformConfig instance

        Returns:
            MRP in minutes
        """
        # Get response times based on configuration scope
        if config.mrp_calculation_scope == "current_round":
            response_times = self.get_response_times()
        elif config.mrp_calculation_scope == "last_X_rounds":
            # Get last X rounds including current
            rounds = self.discussion.rounds.filter(round_number__lte=self.round_number).order_by(
                "-round_number"
            )[: config.mrp_calculation_x_rounds]
            response_times = []
            for round in rounds:
                response_times.extend(round.get_response_times())
        else:  # all_rounds
            rounds = self.discussion.rounds.filter(round_number__lte=self.round_number)
            response_times = []
            for round in rounds:
                response_times.extend(round.get_response_times())

        if not response_times:
            # No response times yet, use default
            return float(self.discussion.min_response_time_minutes)

        # Calculate median
        median = statistics.median(response_times)

        # Apply RTM multiplier
        mrp = median * self.discussion.response_time_multiplier

        # Clamp to MRM bounds
        mrp = max(self.discussion.min_response_time_minutes, mrp)

        return mrp

    def is_expired(self) -> bool:
        """Check if the round has expired based on MRP."""
        if not self.final_mrp_minutes or self.status != "in_progress":
            return False

        # Get time of last response
        last_response = self.responses.order_by("-created_at").first()
        if not last_response:
            # Check against round start time
            elapsed = (timezone.now() - self.start_time).total_seconds() / 60
            return elapsed >= self.final_mrp_minutes

        elapsed = (timezone.now() - last_response.created_at).total_seconds() / 60
        return elapsed >= self.final_mrp_minutes

    def get_response_times(self) -> List[float]:
        """
        Get all time-since-previous values for responses in this round.

        Returns:
            List of response times in minutes
        """
        return list(
            self.responses.filter(time_since_previous_minutes__isnull=False).values_list(
                "time_since_previous_minutes", flat=True
            )
        )

    def __str__(self):
        return f"Round {self.round_number} of {self.discussion.topic_headline}"


class Response(models.Model):
    """
    Represents a user's response in a round.

    Tracks content, timing, edits, and locking status.
    """

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="responses")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="responses")

    content = models.TextField()
    character_count = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    last_edited_at = models.DateTimeField(null=True, blank=True)

    edit_count = models.IntegerField(default=0)
    characters_changed_total = models.IntegerField(default=0)

    time_since_previous_minutes = models.FloatField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)

    class Meta:
        db_table = "responses"
        indexes = [
            models.Index(fields=["round", "user"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs):
        """Auto-calculate character count."""
        self.character_count = len(self.content)
        super().save(*args, **kwargs)

    def can_edit(self, config: PlatformConfig) -> Tuple[bool, Optional[str]]:
        """
        Check if response can be edited.

        Returns:
            Tuple of (can_edit: bool, reason: str or None)
        """
        if self.is_locked:
            return False, "Response is locked"

        if self.edit_count >= config.response_edit_limit:
            return False, f"Maximum {config.response_edit_limit} edits reached"

        # Check 20% character change rule
        max_chars_changeable = (self.character_count * config.response_edit_percentage) // 100
        chars_remaining = max_chars_changeable - self.characters_changed_total

        if chars_remaining <= 0:
            return False, f"Maximum {config.response_edit_percentage}% character change reached"

        return True, None

    def __str__(self):
        return f"Response by {self.user.username} in Round {self.round.round_number}"


class Vote(models.Model):
    """
    Tracks inter-round parameter voting (MRL and RTM).

    Users vote to increase, decrease, or maintain response parameters.
    """

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="votes")

    mrl_vote = models.CharField(
        max_length=20,
        choices=[
            ("increase", "Increase"),
            ("no_change", "No Change"),
            ("decrease", "Decrease"),
        ],
    )

    rtm_vote = models.CharField(
        max_length=20,
        choices=[
            ("increase", "Increase"),
            ("no_change", "No Change"),
            ("decrease", "Decrease"),
        ],
    )

    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "votes"
        unique_together = [["round", "user"]]
        indexes = [
            models.Index(fields=["round", "user"]),
        ]

    def __str__(self):
        return f"Vote by {self.user.username} in Round {self.round.round_number}"


class RemovalVote(models.Model):
    """
    Tracks vote-based moderation removal votes.

    When majority of participants vote to remove someone, they become
    a permanent observer.
    """

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="removal_votes")
    voter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="removal_votes_cast")
    target = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="removal_votes_received"
    )

    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "removal_votes"
        unique_together = [["round", "voter", "target"]]
        indexes = [
            models.Index(fields=["round", "voter"]),
            models.Index(fields=["round", "target"]),
        ]

    def __str__(self):
        return f"{self.voter.username} voted to remove {self.target.username}"


class ModerationAction(models.Model):
    """
    Records all moderation actions in discussions.

    Tracks both mutual removals and vote-based removals.
    """

    discussion = models.ForeignKey(
        Discussion, on_delete=models.CASCADE, related_name="moderation_actions"
    )

    action_type = models.CharField(
        max_length=30,
        choices=[
            ("mutual_removal", "Mutual Removal"),
            ("vote_based_removal", "Vote Based Removal"),
        ],
    )

    initiator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="moderation_actions_initiated"
    )
    target = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="moderation_actions_received"
    )
    round_occurred = models.ForeignKey(
        Round, on_delete=models.CASCADE, related_name="moderation_actions"
    )

    is_permanent = models.BooleanField()
    action_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "moderation_actions"
        indexes = [
            models.Index(fields=["discussion", "action_type"]),
            models.Index(fields=["initiator"]),
            models.Index(fields=["target"]),
        ]

    def __str__(self):
        return f"{self.action_type}: {self.initiator.username} -> {self.target.username}"


class Invite(models.Model):
    """
    Tracks platform and discussion invites.

    Manages invite lifecycle from sent to accepted/declined/expired.
    """

    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invites_sent")
    invitee = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="invites_received"
    )

    invite_type = models.CharField(
        max_length=20,
        choices=[
            ("platform", "Platform"),
            ("discussion", "Discussion"),
        ],
    )

    discussion = models.ForeignKey(
        Discussion, on_delete=models.CASCADE, null=True, blank=True, related_name="invites"
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("sent", "Sent"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
            ("expired", "Expired"),
        ],
        default="sent",
    )

    sent_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    first_participation_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "invites"
        indexes = [
            models.Index(fields=["inviter", "status"]),
            models.Index(fields=["invitee", "status"]),
            models.Index(fields=["discussion"]),
        ]

    def __str__(self):
        invitee_name = self.invitee.username if self.invitee else "pending"
        return f"{self.invite_type} invite from {self.inviter.username} to {invitee_name}"


class JoinRequest(models.Model):
    """
    Tracks requests to join discussions.

    Users can request to join discussions, which must be approved by
    the initiator or delegated approver.
    """

    discussion = models.ForeignKey(
        Discussion, on_delete=models.CASCADE, related_name="join_requests"
    )
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name="join_requests_made")
    approver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="join_requests_to_approve"
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("declined", "Declined"),
        ],
        default="pending",
    )

    request_message = models.TextField(blank=True)
    response_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "join_requests"
        indexes = [
            models.Index(fields=["discussion", "status"]),
            models.Index(fields=["requester", "status"]),
        ]

    def __str__(self):
        return f"Join request by {self.requester.username} for {self.discussion.topic_headline}"


class ResponseEdit(models.Model):
    """
    Tracks individual edits to responses.

    Limited to 2 edits per response with 20% character change limit.
    """

    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="edits")
    edit_number = models.IntegerField(choices=[(1, "1"), (2, "2")])

    previous_content = models.TextField()
    new_content = models.TextField()
    characters_changed = models.IntegerField()

    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "response_edits"
        unique_together = [["response", "edit_number"]]
        indexes = [
            models.Index(fields=["response", "edited_at"]),
        ]

    def __str__(self):
        return f"Edit #{self.edit_number} of response by {self.response.user.username}"


class DraftResponse(models.Model):
    """
    Stores draft responses that weren't submitted.

    Drafts are saved when MRP expires, user manually saves, or round ends.
    """

    discussion = models.ForeignKey(
        Discussion, on_delete=models.CASCADE, related_name="draft_responses"
    )
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="draft_responses")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="draft_responses")

    content = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    saved_reason = models.CharField(
        max_length=20,
        choices=[
            ("mrp_expired", "MRP Expired"),
            ("user_saved", "User Saved"),
            ("round_ended", "Round Ended"),
        ],
    )

    class Meta:
        db_table = "draft_responses"
        indexes = [
            models.Index(fields=["discussion", "round", "user"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"Draft by {self.user.username} in Round {self.round.round_number}"


class NotificationPreference(models.Model):
    """
    User preferences for notification types and delivery methods.

    Controls which notifications users receive and how they receive them
    (email, push, in-app).
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notification_preferences"
    )

    notification_type = models.CharField(
        max_length=50,
        choices=[
            ("new_response", "New Response"),
            ("round_ending_soon", "Round Ending Soon"),
            ("voting_phase_started", "Voting Phase Started"),
            ("parameter_changed", "Parameter Changed"),
            ("became_observer", "Became Observer"),
            ("can_rejoin", "Can Rejoin"),
            ("invite_received", "Invite Received"),
            ("join_request", "Join Request"),
            ("join_approved", "Join Approved"),
            ("discussion_archived", "Discussion Archived"),
        ],
    )

    enabled = models.BooleanField(default=True)
    delivery_method = models.JSONField(
        default=dict, help_text="JSON with keys: email, push, in_app"
    )

    class Meta:
        db_table = "notification_preferences"
        unique_together = [["user", "notification_type"]]
        indexes = [
            models.Index(fields=["user", "enabled"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.notification_type} ({'enabled' if self.enabled else 'disabled'})"
