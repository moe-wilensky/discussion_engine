"""
Comprehensive tests for Discussion Engine models.

Tests cover:
- Model creation and validation
- User invite tracking
- PlatformConfig singleton behavior
- Discussion participant role transitions
- Observer reentry logic
- Invite consumption triggers
- Response edit limits
- MRP calculation algorithm
- Round status transitions
- Vote counting and majority logic
- Moderation action tracking
- Edge cases
"""

import pytest
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from core.models import (
    User,
    PlatformConfig,
    Discussion,
    DiscussionParticipant,
    Round,
    Response,
    Vote,
    RemovalVote,
    ModerationAction,
    Invite,
    JoinRequest,
    ResponseEdit,
    DraftResponse,
    NotificationPreference,
)


@pytest.mark.django_db
class TestUserModel:
    """Tests for the User model."""

    def test_create_user(self, user_factory):
        """Test basic user creation."""
        user = user_factory(username="testuser", phone_number="+15551234567")
        assert user.username == "testuser"
        assert user.phone_number == "+15551234567"
        assert user.platform_invites_banked == 0
        assert user.discussion_invites_banked == 0

    def test_phone_number_unique(self, user_factory):
        """Test that phone numbers must be unique."""
        user_factory(phone_number="+15551234567")
        with pytest.raises(IntegrityError):
            user_factory(phone_number="+15551234567")

    def test_invite_tracking_invariant(self, user):
        """Test that acquired = used + banked."""
        user.earn_invite("platform")
        user.earn_invite("platform")
        user.earn_invite("discussion")

        assert user.platform_invites_acquired == 2
        assert user.platform_invites_banked == 2
        assert user.platform_invites_used == 0

        user.consume_invite("platform")
        user.refresh_from_db()

        assert user.platform_invites_acquired == 2
        assert user.platform_invites_banked == 1
        assert user.platform_invites_used == 1
        # Invariant: acquired = used + banked
        assert (
            user.platform_invites_acquired
            == user.platform_invites_used + user.platform_invites_banked
        )

    def test_can_send_platform_invite(self, user):
        """Test invite availability check."""
        assert not user.can_send_platform_invite()

        user.earn_invite("platform")
        assert user.can_send_platform_invite()

        user.consume_invite("platform")
        assert not user.can_send_platform_invite()

    def test_can_send_discussion_invite(self, user):
        """Test discussion invite availability."""
        assert not user.can_send_discussion_invite()

        user.earn_invite("discussion")
        assert user.can_send_discussion_invite()

        user.consume_invite("discussion")
        assert not user.can_send_discussion_invite()

    def test_consume_invite_without_balance(self, user):
        """Test that consuming without balance raises error."""
        with pytest.raises(ValidationError, match="No platform invites available"):
            user.consume_invite("platform")

        with pytest.raises(ValidationError, match="No discussion invites available"):
            user.consume_invite("discussion")

    def test_invalid_invite_type(self, user):
        """Test that invalid invite types raise error."""
        with pytest.raises(ValueError, match="Invalid invite_type"):
            user.earn_invite("invalid")

        with pytest.raises(ValueError, match="Invalid invite_type"):
            user.consume_invite("invalid")


@pytest.mark.django_db
class TestPlatformConfig:
    """Tests for PlatformConfig singleton."""

    def test_singleton_behavior(self):
        """Test that only one config instance exists."""
        config1 = PlatformConfig.load()
        config2 = PlatformConfig.load()

        assert config1.pk == config2.pk == 1
        assert PlatformConfig.objects.count() == 1

    def test_default_values(self, config):
        """Test that default configuration values are set."""
        assert config.new_user_platform_invites == 3
        assert config.new_user_discussion_invites == 5
        assert config.max_discussion_participants == 10
        assert config.response_edit_limit == 2
        assert config.response_edit_percentage == 20

    def test_cannot_delete_singleton(self, config):
        """Test that singleton cannot be deleted."""
        config.delete()
        assert PlatformConfig.objects.count() == 1

    def test_config_updates_persist(self, config):
        """Test that configuration updates work."""
        config.max_discussion_participants = 20
        config.save()

        config_reloaded = PlatformConfig.load()
        assert config_reloaded.max_discussion_participants == 20


@pytest.mark.django_db
class TestDiscussionModel:
    """Tests for Discussion model."""

    def test_create_discussion(self, discussion_factory, user_factory):
        """Test discussion creation."""
        user = user_factory()
        discussion = discussion_factory(
            initiator=user,
            topic_headline="Climate Change Solutions",
            max_response_length_chars=1000,
            response_time_multiplier=1.5,
            min_response_time_minutes=10,
        )

        assert discussion.topic_headline == "Climate Change Solutions"
        assert discussion.initiator == user
        assert discussion.status == "active"
        assert discussion.max_response_length_chars == 1000
        assert discussion.response_time_multiplier == 1.5
        assert discussion.min_response_time_minutes == 10

    def test_is_at_participant_cap(self, discussion_factory, user_factory, config):
        """Test participant cap checking."""
        discussion = discussion_factory()

        # Initially just the initiator
        assert not discussion.is_at_participant_cap()

        # Add participants up to cap
        for i in range(config.max_discussion_participants - 1):
            user = user_factory()
            DiscussionParticipant.objects.create(discussion=discussion, user=user, role="active")

        assert discussion.is_at_participant_cap()

    def test_get_active_participants(self, discussion_factory, user_factory):
        """Test getting active participants excludes observers."""
        discussion = discussion_factory()

        # Add active participants
        active1 = user_factory()
        active2 = user_factory()
        DiscussionParticipant.objects.create(discussion=discussion, user=active1, role="active")
        DiscussionParticipant.objects.create(discussion=discussion, user=active2, role="active")

        # Add observers
        observer = user_factory()
        DiscussionParticipant.objects.create(
            discussion=discussion, user=observer, role="temporary_observer"
        )

        active_participants = discussion.get_active_participants()
        assert active_participants.count() == 3  # initiator + 2 active
        assert observer not in [p.user for p in active_participants]

    def test_should_archive_duration(self, discussion_factory, config):
        """Test archival based on duration."""
        discussion = discussion_factory()

        # Fresh discussion should not archive
        should_archive, reason = discussion.should_archive()
        assert not should_archive

        # Simulate old discussion
        discussion.created_at = timezone.now() - timedelta(
            days=config.max_discussion_duration_days + 1
        )
        discussion.save()

        should_archive, reason = discussion.should_archive()
        assert should_archive
        assert "duration" in reason.lower()

    def test_should_archive_round_count(self, discussion_factory, round_factory, config):
        """Test archival based on round count."""
        discussion = discussion_factory()

        # Create maximum rounds
        for i in range(config.max_discussion_rounds):
            round_factory(discussion=discussion, round_number=i + 1)

        should_archive, reason = discussion.should_archive()
        assert should_archive
        assert "rounds" in reason.lower()

    def test_should_archive_response_count(
        self, discussion_factory, round_factory, user_factory, config
    ):
        """Test archival based on response count."""
        discussion = discussion_factory()
        round = round_factory(discussion=discussion)

        # Create maximum responses using same user to avoid unique constraint issues
        user = user_factory()
        for i in range(config.max_discussion_responses):
            Response.objects.create(
                round=round,
                user=user,
                content=f"Response {i} with unique content to avoid any issues",
                character_count=10,
            )

        should_archive, reason = discussion.should_archive()
        assert should_archive
        assert "responses" in reason.lower()


@pytest.mark.django_db
class TestDiscussionParticipant:
    """Tests for DiscussionParticipant model."""

    def test_unique_constraint(self, discussion_factory, user_factory):
        """Test that user can only be in discussion once."""
        discussion = discussion_factory()
        user = user_factory()

        DiscussionParticipant.objects.create(discussion=discussion, user=user, role="active")

        with pytest.raises(IntegrityError):
            DiscussionParticipant.objects.create(discussion=discussion, user=user, role="active")

    def test_observer_reentry_mrp_expired_posted(self, discussion_factory, user_factory):
        """Test observer can rejoin immediately if posted in removal round."""
        discussion = discussion_factory()
        user = user_factory()

        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="temporary_observer",
            observer_reason="mrp_expired",
            observer_since=timezone.now(),
            posted_in_round_when_removed=True,
        )

        assert participant.can_rejoin()

    def test_observer_reentry_mrp_expired_not_posted(
        self, discussion_factory, user_factory, round_factory
    ):
        """Test observer must wait for next round if didn't post."""
        discussion = discussion_factory()
        user = user_factory()

        # Create removal round
        removal_round = round_factory(discussion=discussion, round_number=1)

        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="temporary_observer",
            observer_reason="mrp_expired",
            observer_since=removal_round.start_time,
            posted_in_round_when_removed=False,
        )

        # Still in same round - cannot rejoin
        assert not participant.can_rejoin()

        # New round started - can rejoin
        current_round = round_factory(discussion=discussion, round_number=2, status="in_progress")
        assert participant.can_rejoin()

    def test_observer_reentry_mutual_removal_first_time(self, discussion_factory, user_factory):
        """Test first mutual removal has 24hr wait."""
        discussion = discussion_factory()
        user = user_factory()

        now = timezone.now()
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="temporary_observer",
            observer_reason="mutual_removal",
            observer_since=now - timedelta(hours=23),
            removal_count=1,
        )

        # Not enough time passed
        assert not participant.can_rejoin()

        # Update to 24+ hours ago
        participant.observer_since = now - timedelta(hours=25)
        participant.save()

        assert participant.can_rejoin()

    def test_observer_reentry_mutual_removal_second_time(self, discussion_factory, user_factory):
        """Test second mutual removal has 7 day wait."""
        discussion = discussion_factory()
        user = user_factory()

        now = timezone.now()
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="temporary_observer",
            observer_reason="mutual_removal",
            observer_since=now - timedelta(days=6),
            removal_count=2,
        )

        # Not enough time passed
        assert not participant.can_rejoin()

        # Update to 7+ days ago
        participant.observer_since = now - timedelta(days=8)
        participant.save()

        assert participant.can_rejoin()

    def test_observer_reentry_mutual_removal_third_time(self, discussion_factory, user_factory):
        """Test third mutual removal is effectively permanent."""
        discussion = discussion_factory()
        user = user_factory()

        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="temporary_observer",
            observer_reason="mutual_removal",
            observer_since=timezone.now() - timedelta(days=400),
            removal_count=3,
        )

        # Even after a year, cannot rejoin (365 day wait)
        assert not participant.can_rejoin()

    def test_observer_reentry_vote_based_removal(self, discussion_factory, user_factory):
        """Test vote-based removal is permanent."""
        discussion = discussion_factory()
        user = user_factory()

        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="permanent_observer",
            observer_reason="vote_based_removal",
            observer_since=timezone.now() - timedelta(days=365),
        )

        assert not participant.can_rejoin()

    def test_get_wait_period_end(self, discussion_factory, user_factory):
        """Test wait period calculation."""
        discussion = discussion_factory()
        user = user_factory()

        now = timezone.now()
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="temporary_observer",
            observer_reason="mutual_removal",
            observer_since=now,
            removal_count=1,
        )

        wait_end = participant.get_wait_period_end()
        expected_end = now + timedelta(hours=24)

        # Allow 1 second tolerance
        assert abs((wait_end - expected_end).total_seconds()) < 1


@pytest.mark.django_db
class TestRoundModel:
    """Tests for Round model."""

    def test_create_round(self, discussion_factory, round_factory):
        """Test round creation."""
        discussion = discussion_factory()
        round = round_factory(discussion=discussion, round_number=1)

        assert round.discussion == discussion
        assert round.round_number == 1
        assert round.status == "in_progress"

    def test_unique_round_number_per_discussion(self, discussion_factory, round_factory):
        """Test that round numbers are unique within a discussion."""
        discussion = discussion_factory()
        round_factory(discussion=discussion, round_number=1)

        with pytest.raises(IntegrityError):
            round_factory(discussion=discussion, round_number=1)

    def test_calculate_mrp_no_responses(self, round_factory, config):
        """Test MRP calculation with no responses defaults to MRM."""
        round = round_factory()
        mrp = round.calculate_mrp(config)

        assert mrp == float(round.discussion.min_response_time_minutes)

    def test_calculate_mrp_current_round(self, round_factory, user_factory, config):
        """Test MRP calculation for current round scope."""
        config.mrp_calculation_scope = "current_round"
        config.save()

        round = round_factory()

        # Create responses with varying times
        times = [10.0, 20.0, 30.0, 40.0, 50.0]
        for time in times:
            user = user_factory()
            Response.objects.create(
                round=round,
                user=user,
                content="Test response",
                character_count=13,
                time_since_previous_minutes=time,
            )

        mrp = round.calculate_mrp(config)

        # Median of [10, 20, 30, 40, 50] = 30
        # MRP = median * RTM = 30 * 1.0 = 30
        assert mrp == 30.0

    def test_calculate_mrp_with_rtm(self, round_factory, user_factory, config):
        """Test MRP calculation applies RTM multiplier."""
        config.mrp_calculation_scope = "current_round"
        config.save()

        round = round_factory()
        round.discussion.response_time_multiplier = 1.5
        round.discussion.save()

        # Create responses
        for time in [10.0, 20.0, 30.0]:
            user = user_factory()
            Response.objects.create(
                round=round,
                user=user,
                content="Test",
                character_count=4,
                time_since_previous_minutes=time,
            )

        mrp = round.calculate_mrp(config)

        # Median of [10, 20, 30] = 20
        # MRP = 20 * 1.5 = 30
        assert mrp == 30.0

    def test_calculate_mrp_clamped_to_mrm(self, round_factory, user_factory, config):
        """Test MRP is clamped to minimum (MRM)."""
        config.mrp_calculation_scope = "current_round"
        config.save()

        round = round_factory()
        round.discussion.min_response_time_minutes = 100
        round.discussion.response_time_multiplier = 0.5
        round.discussion.save()

        # Create responses with low times
        for time in [10.0, 20.0, 30.0]:
            user = user_factory()
            Response.objects.create(
                round=round,
                user=user,
                content="Test",
                character_count=4,
                time_since_previous_minutes=time,
            )

        mrp = round.calculate_mrp(config)

        # Median = 20, MRP would be 20 * 0.5 = 10
        # But MRM is 100, so MRP = 100
        assert mrp == 100

    def test_calculate_mrp_last_x_rounds(
        self, discussion_factory, round_factory, user_factory, config
    ):
        """Test MRP calculation over last X rounds."""
        config.mrp_calculation_scope = "last_X_rounds"
        config.mrp_calculation_x_rounds = 2
        config.save()

        discussion = discussion_factory()

        # Round 1 with times [10, 20]
        round1 = round_factory(discussion=discussion, round_number=1)
        for time in [10.0, 20.0]:
            user = user_factory()
            Response.objects.create(
                round=round1,
                user=user,
                content="Test",
                character_count=4,
                time_since_previous_minutes=time,
            )

        # Round 2 with times [30, 40]
        round2 = round_factory(discussion=discussion, round_number=2)
        for time in [30.0, 40.0]:
            user = user_factory()
            Response.objects.create(
                round=round2,
                user=user,
                content="Test",
                character_count=4,
                time_since_previous_minutes=time,
            )

        # Round 3 - should use last 2 rounds (2 and 3)
        round3 = round_factory(discussion=discussion, round_number=3)
        for time in [50.0, 60.0]:
            user = user_factory()
            Response.objects.create(
                round=round3,
                user=user,
                content="Test",
                character_count=4,
                time_since_previous_minutes=time,
            )

        mrp = round3.calculate_mrp(config)

        # Times from rounds 2 and 3: [30, 40, 50, 60]
        # Median = 45
        assert mrp == 45.0

    def test_is_expired_no_mrp(self, round_factory):
        """Test round not expired if MRP not set."""
        round = round_factory()
        assert not round.is_expired()

    def test_is_expired_with_response(self, round_factory, user_factory):
        """Test round expiration based on last response time."""
        round = round_factory()
        round.final_mrp_minutes = 60.0  # 1 hour
        round.save()

        # Create response 2 hours ago
        user = user_factory()
        response = Response.objects.create(
            round=round, user=user, content="Test", character_count=4
        )
        response.created_at = timezone.now() - timedelta(hours=2)
        response.save()

        assert round.is_expired()


@pytest.mark.django_db
class TestResponseModel:
    """Tests for Response model."""

    def test_auto_character_count(self, round_factory, user_factory):
        """Test character count is automatically calculated."""
        round = round_factory()
        user = user_factory()

        content = "This is a test response with some content."
        response = Response.objects.create(
            round=round, user=user, content=content, character_count=0  # Will be overwritten
        )

        assert response.character_count == len(content)

    def test_can_edit_locked_response(self, round_factory, user_factory, config):
        """Test locked responses cannot be edited."""
        round = round_factory()
        user = user_factory()

        response = Response.objects.create(
            round=round, user=user, content="Test response", character_count=13, is_locked=True
        )

        can_edit, reason = response.can_edit(config)
        assert not can_edit
        assert "locked" in reason.lower()

    def test_can_edit_max_edits_reached(self, round_factory, user_factory, config):
        """Test max edit limit."""
        round = round_factory()
        user = user_factory()

        response = Response.objects.create(
            round=round, user=user, content="Test response", character_count=13, edit_count=2
        )

        can_edit, reason = response.can_edit(config)
        assert not can_edit
        assert "2 edits" in reason

    def test_can_edit_character_limit(self, round_factory, user_factory, config):
        """Test 20% character change limit."""
        round = round_factory()
        user = user_factory()

        content = "A" * 100
        response = Response.objects.create(
            round=round,
            user=user,
            content=content,
            character_count=100,
            characters_changed_total=20,  # Already used 20%
        )

        can_edit, reason = response.can_edit(config)
        assert not can_edit
        assert "20%" in reason

    def test_can_edit_allowed(self, round_factory, user_factory, config):
        """Test response can be edited when conditions met."""
        round = round_factory()
        user = user_factory()

        response = Response.objects.create(
            round=round,
            user=user,
            content="Test response",
            character_count=100,
            edit_count=0,
            characters_changed_total=0,
            is_locked=False,
        )

        can_edit, reason = response.can_edit(config)
        assert can_edit
        assert reason is None


@pytest.mark.django_db
class TestVoteModel:
    """Tests for Vote model."""

    def test_create_vote(self, round_factory, user_factory):
        """Test vote creation."""
        round = round_factory()
        user = user_factory()

        vote = Vote.objects.create(round=round, user=user, mrl_vote="increase", rtm_vote="decrease")

        assert vote.mrl_vote == "increase"
        assert vote.rtm_vote == "decrease"

    def test_unique_vote_per_user_per_round(self, round_factory, user_factory):
        """Test users can only vote once per round."""
        round = round_factory()
        user = user_factory()

        Vote.objects.create(round=round, user=user, mrl_vote="increase", rtm_vote="no_change")

        with pytest.raises(IntegrityError):
            Vote.objects.create(round=round, user=user, mrl_vote="decrease", rtm_vote="no_change")


@pytest.mark.django_db
class TestRemovalVoteModel:
    """Tests for RemovalVote model."""

    def test_create_removal_vote(self, round_factory, user_factory):
        """Test removal vote creation."""
        round = round_factory()
        voter = user_factory()
        target = user_factory()

        vote = RemovalVote.objects.create(round=round, voter=voter, target=target)

        assert vote.voter == voter
        assert vote.target == target

    def test_vote_based_removal_threshold(
        self, round_factory, user_factory, discussion_factory, config
    ):
        """Test vote-based removal requires majority."""
        discussion = discussion_factory()
        round = round_factory(discussion=discussion)
        target = user_factory()

        # Create 5 active participants + initiator = 6 total
        participants = [user_factory() for _ in range(5)]
        for user in participants:
            DiscussionParticipant.objects.create(discussion=discussion, user=user, role="active")

        # Add target as participant
        DiscussionParticipant.objects.create(discussion=discussion, user=target, role="active")

        # Need majority: threshold = 0.5, so need > 50%
        # Total active (excluding target) = 6
        # Need > 3 votes for removal (4/6 = 0.666 > 0.5)

        # Create 3 votes - exactly at threshold, not enough (need >)
        for i in range(3):
            RemovalVote.objects.create(round=round, voter=participants[i], target=target)

        votes = RemovalVote.objects.filter(round=round, target=target).count()
        active_count = discussion.get_active_participants().exclude(user=target).count()
        vote_ratio = votes / active_count if active_count > 0 else 0

        # 3/6 = 0.5, which equals threshold, so not enough (need >)
        assert vote_ratio <= config.vote_based_removal_threshold

        # Add one more vote - now enough
        RemovalVote.objects.create(round=round, voter=participants[3], target=target)

        votes = RemovalVote.objects.filter(round=round, target=target).count()
        vote_ratio = votes / active_count

        assert vote_ratio > config.vote_based_removal_threshold


@pytest.mark.django_db
class TestModerationAction:
    """Tests for ModerationAction model."""

    def test_create_moderation_action(self, discussion_factory, round_factory, user_factory):
        """Test moderation action creation."""
        discussion = discussion_factory()
        round = round_factory(discussion=discussion)
        initiator = user_factory()
        target = user_factory()

        action = ModerationAction.objects.create(
            discussion=discussion,
            action_type="mutual_removal",
            initiator=initiator,
            target=target,
            round_occurred=round,
            is_permanent=False,
        )

        assert action.action_type == "mutual_removal"
        assert not action.is_permanent

    def test_vote_based_removal_is_permanent(self, discussion_factory, round_factory, user_factory):
        """Test vote-based removals are permanent."""
        discussion = discussion_factory()
        round = round_factory(discussion=discussion)
        initiator = user_factory()
        target = user_factory()

        action = ModerationAction.objects.create(
            discussion=discussion,
            action_type="vote_based_removal",
            initiator=initiator,
            target=target,
            round_occurred=round,
            is_permanent=True,
        )

        assert action.is_permanent


@pytest.mark.django_db
class TestInviteModel:
    """Tests for Invite model."""

    def test_create_platform_invite(self, user_factory):
        """Test platform invite creation."""
        inviter = user_factory()
        invitee = user_factory()

        invite = Invite.objects.create(
            inviter=inviter, invitee=invitee, invite_type="platform", status="sent"
        )

        assert invite.invite_type == "platform"
        assert invite.status == "sent"

    def test_create_discussion_invite(self, user_factory, discussion_factory):
        """Test discussion invite with discussion reference."""
        inviter = user_factory()
        invitee = user_factory()
        discussion = discussion_factory()

        invite = Invite.objects.create(
            inviter=inviter,
            invitee=invitee,
            invite_type="discussion",
            discussion=discussion,
            status="sent",
        )

        assert invite.discussion == discussion

    def test_invite_consumption_on_send(self, user_factory, config):
        """Test invite consumed when sent if trigger is 'sent'."""
        config.invite_consumption_trigger = "sent"
        config.save()

        inviter = user_factory()
        inviter.earn_invite("platform")

        assert inviter.platform_invites_banked == 1

        # Simulate consuming on send
        inviter.consume_invite("platform")

        Invite.objects.create(inviter=inviter, invitee=None, invite_type="platform", status="sent")

        assert inviter.platform_invites_banked == 0

    def test_invite_consumption_on_accept(self, user_factory, config):
        """Test invite consumed when accepted if trigger is 'accepted'."""
        config.invite_consumption_trigger = "accepted"
        config.save()

        inviter = user_factory()
        invitee = user_factory()
        inviter.earn_invite("platform")

        # Create invite
        invite = Invite.objects.create(
            inviter=inviter, invitee=invitee, invite_type="platform", status="sent"
        )

        # Still have invite until accepted
        assert inviter.platform_invites_banked == 1

        # Accept invite
        inviter.consume_invite("platform")
        invite.status = "accepted"
        invite.accepted_at = timezone.now()
        invite.save()

        assert inviter.platform_invites_banked == 0


@pytest.mark.django_db
class TestJoinRequest:
    """Tests for JoinRequest model."""

    def test_create_join_request(self, discussion_factory, user_factory):
        """Test join request creation."""
        discussion = discussion_factory()
        requester = user_factory()

        request = JoinRequest.objects.create(
            discussion=discussion,
            requester=requester,
            approver=discussion.initiator,
            request_message="I'd like to join this discussion.",
        )

        assert request.status == "pending"
        assert request.approver == discussion.initiator


@pytest.mark.django_db
class TestResponseEdit:
    """Tests for ResponseEdit model."""

    def test_create_response_edit(self, round_factory, user_factory):
        """Test response edit tracking."""
        round = round_factory()
        user = user_factory()

        response = Response.objects.create(
            round=round, user=user, content="Original content", character_count=16
        )

        edit = ResponseEdit.objects.create(
            response=response,
            edit_number=1,
            previous_content="Original content",
            new_content="Edited content",
            characters_changed=5,
        )

        assert edit.edit_number == 1
        assert edit.characters_changed == 5


@pytest.mark.django_db
class TestDraftResponse:
    """Tests for DraftResponse model."""

    def test_create_draft_response(self, discussion_factory, round_factory, user_factory):
        """Test draft response creation."""
        discussion = discussion_factory()
        round = round_factory(discussion=discussion)
        user = user_factory()

        draft = DraftResponse.objects.create(
            discussion=discussion,
            round=round,
            user=user,
            content="Draft content",
            saved_reason="mrp_expired",
        )

        assert draft.saved_reason == "mrp_expired"


@pytest.mark.django_db
class TestNotificationPreference:
    """Tests for NotificationPreference model."""

    def test_create_notification_preference(self, user_factory):
        """Test notification preference creation."""
        user = user_factory()

        pref = NotificationPreference.objects.create(
            user=user,
            notification_type="new_response",
            enabled=True,
            delivery_method={"email": True, "push": False, "in_app": True},
        )

        assert pref.enabled
        assert pref.delivery_method["email"]
        assert not pref.delivery_method["push"]

    def test_unique_preference_per_user_type(self, user_factory):
        """Test user can only have one preference per notification type."""
        user = user_factory()

        NotificationPreference.objects.create(
            user=user, notification_type="new_response", enabled=True
        )

        with pytest.raises(IntegrityError):
            NotificationPreference.objects.create(
                user=user, notification_type="new_response", enabled=False
            )


@pytest.mark.django_db
class TestEdgeCases:
    """Tests for edge cases and complex scenarios."""

    def test_multiple_discussions_same_topic(self, discussion_factory, config):
        """Test handling of duplicate discussion topics."""
        # When allow_duplicate_discussions is False
        config.allow_duplicate_discussions = False
        config.save()

        # Can create discussions with same topic (enforcement would be at API level)
        d1 = discussion_factory(topic_headline="Climate Change")
        d2 = discussion_factory(topic_headline="Climate Change")

        assert d1.pk != d2.pk

    def test_removal_escalation(self, discussion_factory, user_factory):
        """Test escalating removal wait periods."""
        discussion = discussion_factory()
        user = user_factory()

        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role="temporary_observer",
            observer_reason="mutual_removal",
            observer_since=timezone.now(),
            removal_count=0,
        )

        # Simulate multiple removals
        wait_periods = []
        for count in [1, 2, 3]:
            participant.removal_count = count
            participant.observer_since = timezone.now()
            participant.save()

            wait_end = participant.get_wait_period_end()
            if wait_end:
                wait_duration = wait_end - participant.observer_since
                wait_periods.append(wait_duration.total_seconds())

        # Wait periods should increase
        assert wait_periods[0] < wait_periods[1] < wait_periods[2]

    def test_concurrent_invites(self, user_factory):
        """Test user can send multiple invites concurrently."""
        user = user_factory()

        # Give user multiple invites
        for _ in range(5):
            user.earn_invite("discussion")

        assert user.discussion_invites_banked == 5

        # Send all invites
        invitees = [user_factory() for _ in range(5)]
        for invitee in invitees:
            user.consume_invite("discussion")
            Invite.objects.create(
                inviter=user, invitee=invitee, invite_type="discussion", status="sent"
            )

        assert user.discussion_invites_banked == 0
        assert user.discussion_invites_used == 5
