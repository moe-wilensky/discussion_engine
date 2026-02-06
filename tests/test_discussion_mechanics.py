"""
Test core discussion mechanics from latest_discusion_mechanics.md

This test module validates the exact mechanics outlined in the specification:
1. New users get 5 platform invites + 25 discussion invites
2. Conversation participants get 0.2 platform invites + 1 discussion invite per response
3. Active participants moved to observer status (MRP timeout) don't receive invite credits on return
4. Users moved to observers via kamikaze miss next full round and don't get invite credits when rejoining
5. Users can't apply kamikaze until both have posted in current round
6. When conversation has ≤1 active participants, it's locked (archived)
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from core.models import (
    User,
    Discussion,
    Round,
    Response,
    DiscussionParticipant,
    Invite,
    PlatformConfig,
)
from core.services.invite_service import InviteService
from core.services.discussion_service import DiscussionService
from core.services.response_service import ResponseService
from core.services.mutual_removal_service import MutualRemovalService
from core.services.round_service import RoundService
from tests.factories import UserFactory, DiscussionFactory, RoundFactory


@pytest.mark.django_db
class TestMechanic1NewUserInvites:
    """Test mechanic 1: New users get 5 platform invites + 25 discussion invites"""

    def test_new_user_receives_initial_invites(self):
        """New user accepting platform invite should get 5 platform + 25 discussion invites"""
        inviter = UserFactory()
        inviter.platform_invites_banked = 10
        inviter.save()

        # Create platform invite
        invite, code = InviteService.send_platform_invite(inviter)

        # Create new user and accept invite
        new_user = UserFactory()
        InviteService.accept_invite(invite, new_user)

        new_user.refresh_from_db()
        config = PlatformConfig.load()

        assert new_user.platform_invites_banked == config.new_user_platform_invites
        assert new_user.discussion_invites_banked == config.new_user_discussion_invites
        assert new_user.platform_invites_acquired == config.new_user_platform_invites
        assert new_user.discussion_invites_acquired == config.new_user_discussion_invites

    def test_config_defaults_for_new_users(self):
        """Verify config defaults match spec: 5 platform, 25 discussion"""
        config = PlatformConfig.load()
        assert config.new_user_platform_invites == 5
        assert config.new_user_discussion_invites == 25


@pytest.mark.django_db
class TestMechanic2InviteCreditsPerResponse:
    """Test mechanic 2: Participants get 0.2 platform + 1 discussion invite per response"""

    def test_response_earns_correct_invite_credits(self):
        """Posting a response should earn 0.2 platform + 1 discussion invite"""
        user = UserFactory()
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="Test Discussion",
            details="Test details",
            mrm=30,
            rtm=1.0,
            mrl=500,
            initial_invites=[],
        )
        round_obj = Round.objects.get(discussion=discussion, round_number=1)

        initial_platform = user.platform_invites_acquired
        initial_discussion = user.discussion_invites_acquired

        # Submit response
        ResponseService.submit_response(
            user=user, round=round_obj, content="Test response for invite credits"
        )

        user.refresh_from_db()
        config = PlatformConfig.load()

        # Check increments
        platform_earned = user.platform_invites_acquired - initial_platform
        discussion_earned = user.discussion_invites_acquired - initial_discussion

        assert platform_earned == Decimal(str(config.platform_invites_per_response))
        assert discussion_earned == Decimal(str(config.discussion_invites_per_response))
        assert platform_earned == Decimal('0.2')
        assert discussion_earned == Decimal('1.0')

    def test_multiple_responses_accumulate_invites(self):
        """Multiple responses should accumulate fractional invites"""
        user = UserFactory()
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="Multi-round Test",
            details="Testing accumulation",
            mrm=30,
            rtm=1.0,
            mrl=500,
            initial_invites=[],
        )

        initial_platform = user.platform_invites_acquired

        # Post in first round (auto-created)
        round1 = Round.objects.get(discussion=discussion, round_number=1)
        ResponseService.submit_response(
            user=user, round=round1, content="Response 1"
        )
        
        # Create and post in additional rounds
        for i in range(2, 6):  # Rounds 2-5
            round_obj = RoundFactory(
                discussion=discussion, round_number=i, status="in_progress"
            )
            ResponseService.submit_response(
                user=user, round=round_obj, content=f"Response {i}"
            )

        user.refresh_from_db()

        # 5 responses * 0.2 = 1.0 platform invite
        expected = initial_platform + Decimal('1.0')
        assert user.platform_invites_acquired == expected
        assert user.platform_invites_banked >= Decimal('1.0')


@pytest.mark.django_db
class TestMechanic3MRPObserverReturnsWithoutCredits:
    """Test mechanic 3: Active participant moved to observer (MRP timeout) doesn't get credits on return"""

    def test_mrp_timeout_observer_skips_credits_on_return(self):
        """User who times out via MRP shouldn't get credits on their first response back"""
        user = UserFactory()
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="MRP Test",
            details="Testing MRP timeout",
            mrm=60,
            rtm=1.0,
            mrl=500,
            initial_invites=[],
        )
        
        round1 = Round.objects.get(discussion=discussion, round_number=1)
        round1.final_mrp_minutes = 60.0
        round1.save()

        participant = DiscussionParticipant.objects.get(discussion=discussion, user=user)

        # User didn't post in round 1, MRP expires, they become observer
        from core.services.observer_service import ObserverService

        ObserverService.move_to_observer(
            participant, reason="mrp_expired", posted_in_round=False
        )
        participant.refresh_from_db()

        # Verify skip flag is set
        assert participant.skip_invite_credits_on_return is True

        # Start round 2
        round2 = RoundFactory(
            discussion=discussion,
            round_number=2,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        initial_platform = user.platform_invites_acquired
        initial_discussion = user.discussion_invites_acquired

        # User posts in round 2 (returns from observer)
        ResponseService.submit_response(
            user=user, round=round2, content="Returning from observer"
        )

        user.refresh_from_db()
        participant.refresh_from_db()

        # First response after observer should NOT earn credits
        assert user.platform_invites_acquired == initial_platform
        assert user.discussion_invites_acquired == initial_discussion

        # Now they're active again
        assert participant.role == "active"
        assert participant.skip_invite_credits_on_return is False

        # Second response SHOULD earn credits
        round3 = RoundFactory(
            discussion=discussion,
            round_number=3,
            status="in_progress",
            final_mrp_minutes=60.0,
        )
        ResponseService.submit_response(
            user=user, round=round3, content="Second response after return"
        )

        user.refresh_from_db()
        assert user.platform_invites_acquired > initial_platform
        assert user.discussion_invites_acquired > initial_discussion


@pytest.mark.django_db
class TestMechanic4KamikazeSkipsCredits:
    """Test mechanic 4: Users removed via kamikaze miss next full round and don't get credits"""

    def test_kamikaze_participants_skip_credits_on_return(self):
        """Both kamikaze users should skip invite credits when they return"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        user_c = UserFactory(username="user_c")  # Add third user to prevent archival

        discussion = DiscussionService.create_discussion(
            initiator=user_a,
            headline="Kamikaze Test",
            details="Testing kamikaze skip credits",
            mrm=30,
            rtm=1.0,
            mrl=500,
            initial_invites=[],
        )

        # Add user_b and user_c as participants
        participant_b = DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )
        participant_c = DiscussionParticipant.objects.create(
            discussion=discussion, user=user_c, role="active"
        )
        participant_a = DiscussionParticipant.objects.get(
            discussion=discussion, user=user_a
        )

        round1 = Round.objects.get(discussion=discussion, round_number=1)
        round1.status = "in_progress"
        round1.save()

        # All users must post before A and B use kamikaze
        Response.objects.create(user=user_a, round=round1, content="A's response", character_count=12)
        Response.objects.create(user=user_b, round=round1, content="B's response", character_count=12)
        Response.objects.create(user=user_c, round=round1, content="C's response", character_count=12)

        # Execute kamikaze
        MutualRemovalService.initiate_removal(
            initiator=user_a, target=user_b, discussion=discussion, current_round=round1
        )

        participant_a.refresh_from_db()
        participant_b.refresh_from_db()

        # Both should have skip flag set
        assert participant_a.skip_invite_credits_on_return is True
        assert participant_b.skip_invite_credits_on_return is True
        assert participant_a.role == "temporary_observer"
        assert participant_b.role == "temporary_observer"

        # Create round 2 (which they will miss)
        round2 = RoundFactory(
            discussion=discussion, round_number=2, status="completed", final_mrp_minutes=60.0
        )

        # Create round 3 (where they can rejoin)
        round3 = RoundFactory(
            discussion=discussion, round_number=3, status="in_progress", final_mrp_minutes=60.0
        )

        # Track initial credits
        initial_a_platform = user_a.platform_invites_acquired
        initial_b_platform = user_b.platform_invites_acquired

        # Both rejoin by posting in round 3
        ResponseService.submit_response(user=user_a, round=round3, content="A returns")
        ResponseService.submit_response(user=user_b, round=round3, content="B returns")

        user_a.refresh_from_db()
        user_b.refresh_from_db()

        # Neither should have earned credits on return
        assert user_a.platform_invites_acquired == initial_a_platform
        assert user_b.platform_invites_acquired == initial_b_platform


@pytest.mark.django_db
class TestMechanic5KamikazeRequiresBothPosted:
    """Test mechanic 5: Can't apply kamikaze until both users have posted in current round"""

    def test_kamikaze_fails_if_initiator_hasnt_posted(self):
        """Kamikaze should fail if initiator hasn't posted yet"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        discussion = DiscussionFactory(initiator=user_a)
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )
        round1 = RoundFactory(discussion=discussion, round_number=1, status="in_progress")

        # Only B has posted
        Response.objects.create(user=user_b, round=round1, content="B's response")

        # A tries kamikaze without posting
        can_remove, reason = MutualRemovalService.can_initiate_removal(
            initiator=user_a, target=user_b, discussion=discussion, current_round=round1
        )

        assert can_remove is False
        assert "must have posted" in reason.lower() or "post" in reason.lower()

    def test_kamikaze_fails_if_target_hasnt_posted(self):
        """Kamikaze should fail if target hasn't posted yet"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        discussion = DiscussionFactory(initiator=user_a)
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )
        round1 = RoundFactory(discussion=discussion, round_number=1, status="in_progress")

        # Only A has posted
        Response.objects.create(user=user_a, round=round1, content="A's response")

        # A tries kamikaze when B hasn't posted
        can_remove, reason = MutualRemovalService.can_initiate_removal(
            initiator=user_a, target=user_b, discussion=discussion, current_round=round1
        )

        assert can_remove is False
        assert "must have posted" in reason.lower() or "post" in reason.lower()

    def test_kamikaze_succeeds_when_both_posted(self):
        """Kamikaze should succeed when both users have posted"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        discussion = DiscussionFactory(initiator=user_a)
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )
        round1 = RoundFactory(discussion=discussion, round_number=1, status="in_progress")

        # Both post
        Response.objects.create(user=user_a, round=round1, content="A's response")
        Response.objects.create(user=user_b, round=round1, content="B's response")

        # Now kamikaze should work
        can_remove, reason = MutualRemovalService.can_initiate_removal(
            initiator=user_a, target=user_b, discussion=discussion, current_round=round1
        )

        assert can_remove is True


@pytest.mark.django_db
class TestMechanic6ConversationLocking:
    """Test mechanic 6: When conversation has ≤1 active participants, it's locked (archived)"""

    def test_discussion_locks_when_one_participant_remains(self):
        """Discussion should be archived when only 1 active participant remains"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        user_c = UserFactory(username="user_c")
        discussion = DiscussionFactory(initiator=user_a)

        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_c, role="active"
        )

        round1 = RoundFactory(discussion=discussion, round_number=1, status="in_progress")

        # All post
        Response.objects.create(user=user_a, round=round1, content="A's response")
        Response.objects.create(user=user_b, round=round1, content="B's response")
        Response.objects.create(user=user_c, round=round1, content="C's response")

        # A kamikazes B (both become observers, leaving only C)
        MutualRemovalService.initiate_removal(
            initiator=user_a, target=user_b, discussion=discussion, current_round=round1
        )

        discussion.refresh_from_db()

        # Discussion should be archived
        assert discussion.status == "archived"
        assert discussion.archived_at is not None

    def test_discussion_locks_when_zero_participants_remain(self):
        """Discussion should be archived when 0 active participants remain"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        discussion = DiscussionFactory(initiator=user_a)

        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )

        round1 = RoundFactory(discussion=discussion, round_number=1, status="in_progress")

        # Both post
        Response.objects.create(user=user_a, round=round1, content="A's response")
        Response.objects.create(user=user_b, round=round1, content="B's response")

        # A kamikazes B (both become observers, 0 active remain)
        MutualRemovalService.initiate_removal(
            initiator=user_a, target=user_b, discussion=discussion, current_round=round1
        )

        discussion.refresh_from_db()

        # Discussion should be archived
        assert discussion.status == "archived"
        assert discussion.archived_at is not None

    def test_discussion_locks_via_mrp_expiration(self):
        """Discussion should be archived when MRP expiration leaves ≤1 active"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        discussion = DiscussionFactory(initiator=user_a)

        participant_b = DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )

        round1 = RoundFactory(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        # Only A posts
        Response.objects.create(user=user_a, round=round1, content="A's response")

        # MRP expires, B becomes observer
        RoundService.handle_mrp_expiration(round1)

        discussion.refresh_from_db()

        # Should be archived (only 1 active remains)
        assert discussion.status == "archived"
        assert discussion.archived_at is not None

    def test_discussion_stays_active_with_two_participants(self):
        """Discussion should stay active with 2+ active participants"""
        user_a = UserFactory(username="user_a")
        user_b = UserFactory(username="user_b")
        user_c = UserFactory(username="user_c")
        user_d = UserFactory(username="user_d")
        discussion = DiscussionFactory(initiator=user_a)

        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_b, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_c, role="active"
        )
        DiscussionParticipant.objects.create(
            discussion=discussion, user=user_d, role="active"
        )

        round1 = RoundFactory(discussion=discussion, round_number=1, status="in_progress")

        # All post
        Response.objects.create(user=user_a, round=round1, content="A's response")
        Response.objects.create(user=user_b, round=round1, content="B's response")
        Response.objects.create(user=user_c, round=round1, content="C's response")
        Response.objects.create(user=user_d, round=round1, content="D's response")

        # A kamikazes B (both become observers, C and D remain active)
        MutualRemovalService.initiate_removal(
            initiator=user_a, target=user_b, discussion=discussion, current_round=round1
        )

        discussion.refresh_from_db()

        # Discussion should still be active (2 active participants remain)
        assert discussion.status == "active"
        assert discussion.archived_at is None
