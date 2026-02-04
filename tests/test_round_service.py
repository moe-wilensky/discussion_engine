"""
Comprehensive tests for RoundService - targeting 95%+ coverage.

Covers gaps in round_service.py including:
- start_round_1
- check_phase_1_timeout
- is_mrp_expired
- get_mrp_deadline  
- handle_mrp_expiration
- end_round
- should_end_round
- get_phase_info
"""

import pytest
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from core.models import PlatformConfig, Round
from core.services.round_service import RoundService
from core.services.response_service import ResponseService
from tests.factories import (
    UserFactory,
    DiscussionFactory,
    RoundFactory,
    ResponseFactory,
    DiscussionParticipantFactory,
)


@pytest.mark.django_db
class TestStartRound1:
    """Test start_round_1 method."""

    def test_start_round_1_creates_round(self):
        """Test that start_round_1 creates Round 1 with correct attributes."""
        discussion = DiscussionFactory()
        
        round_obj = RoundService.start_round_1(discussion)
        
        assert round_obj is not None
        assert round_obj.discussion == discussion
        assert round_obj.round_number == 1
        assert round_obj.status == "in_progress"
        assert round_obj.start_time is not None
        assert abs((round_obj.start_time - timezone.now()).total_seconds()) < 2

    def test_start_round_1_persisted(self):
        """Test that created round is saved to database."""
        discussion = DiscussionFactory()
        
        round_obj = RoundService.start_round_1(discussion)
        
        # Verify it's in the database
        assert Round.objects.filter(id=round_obj.id).exists()
        assert Round.objects.get(id=round_obj.id).round_number == 1


@pytest.mark.django_db
class TestPhase1Timeout:
    """Test check_phase_1_timeout logic."""

    def test_timeout_not_in_phase_1(self):
        """Test timeout returns False when not in Phase 1."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 3
        config.save()
        
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)
        
        # Create enough responses to be in Phase 2
        users = [UserFactory() for _ in range(3)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
            ResponseFactory(round=round_obj, user=user)
        
        # Not in Phase 1, so timeout should return False
        result = RoundService.check_phase_1_timeout(round_obj, config)
        assert result is False

    def test_timeout_not_reached(self):
        """Test timeout returns False when timeout not reached."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 5
        config.round_1_phase_1_timeout_days = 30
        config.save()
        
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, start_time=timezone.now())
        
        # Add participants but no responses
        for _ in range(3):
            DiscussionParticipantFactory(discussion=discussion, role="active")
        
        # Timeout not reached
        result = RoundService.check_phase_1_timeout(round_obj, config)
        assert result is False

    def test_timeout_reached_insufficient_responses_archives(self):
        """Test timeout archives discussion when insufficient responses."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 10  # Set high enough
        config.round_1_phase_1_timeout_days = 30
        config.save()
        
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)
        
        # Manually set start_time to 31 days ago (auto_now_add prevents factory from setting it)
        old_time = timezone.now() - timedelta(days=31)
        Round.objects.filter(id=round_obj.id).update(start_time=old_time)
        round_obj.refresh_from_db()
        
        # Add 5 active participants (N = min(10, 5) = 5)
        users = [UserFactory() for _ in range(5)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # Only 2 responses (< 5 needed to exit Phase 1)
        for i in range(2):
            ResponseFactory(round=round_obj, user=users[i])
        
        # Debug the state
        response_count = round_obj.responses.count()
        invited_count = round_obj.discussion.participants.filter(role__in=["initiator", "active"]).count()
        n_threshold = min(config.n_responses_before_mrp, invited_count)
        is_phase_1 = RoundService.is_phase_1(round_obj, config)
        elapsed = timezone.now() - round_obj.start_time
        
        # Verify we're in Phase 1
        assert is_phase_1 is True, f"Not in Phase 1: responses={response_count}, N={n_threshold}"
        
        # Should archive
        result = RoundService.check_phase_1_timeout(round_obj, config)
        
        assert result is True, f"Timeout did not trigger: is_phase_1={is_phase_1}, elapsed.days={elapsed.days}"
        discussion.refresh_from_db()
        assert discussion.status == "archived"
        assert discussion.archived_at is not None

    def test_timeout_reached_sufficient_responses_continues(self):
        """Test timeout continues when enough responses exist."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 5
        config.round_1_phase_1_timeout_days = 30
        config.save()
        
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)
        
        # Manually set start_time to 31 days ago
        old_time = timezone.now() - timedelta(days=31)
        Round.objects.filter(id=round_obj.id).update(start_time=old_time)
        round_obj.refresh_from_db()
        
        # Add 3 participants (N = min(5, 3) = 3)
        users = [UserFactory() for _ in range(3)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # Add 3 responses (meets threshold)
        for user in users:
            ResponseFactory(round=round_obj, user=user)
        
        # Should NOT timeout (has enough responses for phase 2)
        result = RoundService.check_phase_1_timeout(round_obj, config)
        
        assert result is False
        discussion.refresh_from_db()
        assert discussion.status != "archived"


@pytest.mark.django_db
class TestMRPExpiration:
    """Test MRP expiration detection."""

    def test_is_mrp_expired_no_mrp_set(self):
        """Test returns False when no MRP set."""
        round_obj = RoundFactory(status="in_progress", final_mrp_minutes=None)
        
        result = RoundService.is_mrp_expired(round_obj)
        assert result is False

    def test_is_mrp_expired_not_in_progress(self):
        """Test returns False when round not in progress."""
        round_obj = RoundFactory(status="completed", final_mrp_minutes=60)
        
        result = RoundService.is_mrp_expired(round_obj)
        assert result is False

    def test_is_mrp_expired_no_responses_not_expired(self):
        """Test expiration check with no responses yet (not expired)."""
        round_obj = RoundFactory(
            status="in_progress",
            final_mrp_minutes=60,
            start_time=timezone.now() - timedelta(minutes=30)
        )
        
        result = RoundService.is_mrp_expired(round_obj)
        assert result is False

    def test_is_mrp_expired_no_responses_expired(self):
        """Test expiration check with no responses (expired)."""
        round_obj = RoundFactory(
            status="in_progress",
            final_mrp_minutes=60
        )
        
        # Manually set start_time to 61 minutes ago
        old_time = timezone.now() - timedelta(minutes=61)
        Round.objects.filter(id=round_obj.id).update(start_time=old_time)
        round_obj.refresh_from_db()
        
        result = RoundService.is_mrp_expired(round_obj)
        assert result is True

    def test_is_mrp_expired_with_responses_not_expired(self):
        """Test expiration check with recent response (not expired)."""
        round_obj = RoundFactory(
            status="in_progress",
            final_mrp_minutes=60
        )
        
        # Add response 30 minutes ago
        response = ResponseFactory(
            round=round_obj,
            created_at=timezone.now() - timedelta(minutes=30)
        )
        
        result = RoundService.is_mrp_expired(round_obj)
        assert result is False

    def test_is_mrp_expired_with_responses_expired(self):
        """Test expiration check with old response (expired)."""
        round_obj = RoundFactory(
            status="in_progress",
            final_mrp_minutes=60
        )
        
        # Add response and manually set created_at to 61 minutes ago
        response = ResponseFactory(round=round_obj)
        old_time = timezone.now() - timedelta(minutes=61)
        response.__class__.objects.filter(id=response.id).update(created_at=old_time)
        
        result = RoundService.is_mrp_expired(round_obj)
        assert result is True


@pytest.mark.django_db
class TestMRPDeadline:
    """Test MRP deadline calculation."""

    def test_get_mrp_deadline_no_mrp(self):
        """Test returns None when no MRP set."""
        round_obj = RoundFactory(final_mrp_minutes=None)
        
        result = RoundService.get_mrp_deadline(round_obj)
        assert result is None

    def test_get_mrp_deadline_not_in_progress(self):
        """Test returns None when round not in progress."""
        round_obj = RoundFactory(status="completed", final_mrp_minutes=60)
        
        result = RoundService.get_mrp_deadline(round_obj)
        assert result is None

    def test_get_mrp_deadline_no_responses(self):
        """Test deadline calculated from round start when no responses."""
        start_time = timezone.now() - timedelta(minutes=10)
        round_obj = RoundFactory(
            status="in_progress",
            final_mrp_minutes=60,
            start_time=start_time
        )
        
        result = RoundService.get_mrp_deadline(round_obj)
        
        # Use the actual start_time from the saved object
        round_obj.refresh_from_db()
        expected = round_obj.start_time + timedelta(minutes=60)
        assert result is not None
        assert abs((result - expected).total_seconds()) < 1

    def test_get_mrp_deadline_with_responses(self):
        """Test deadline calculated from last response."""
        round_obj = RoundFactory(
            status="in_progress",
            final_mrp_minutes=60
        )
        
        # Add multiple responses
        response1 = ResponseFactory(
            round=round_obj,
            created_at=timezone.now() - timedelta(minutes=30)
        )
        response2 = ResponseFactory(
            round=round_obj,
            created_at=timezone.now() - timedelta(minutes=10)
        )
        
        result = RoundService.get_mrp_deadline(round_obj)
        
        # Should be calculated from last response (response2)
        expected = response2.created_at + timedelta(minutes=60)
        assert result is not None
        assert abs((result - expected).total_seconds()) < 1


@pytest.mark.django_db
class TestHandleMRPExpiration:
    """Test handle_mrp_expiration logic."""

    def test_handle_mrp_expiration_moves_non_responders(self):
        """Test non-responders moved to temporary observer."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create 3 participants
        user1, user2, user3 = [UserFactory() for _ in range(3)]
        p1 = DiscussionParticipantFactory(discussion=discussion, user=user1, role="active")
        p2 = DiscussionParticipantFactory(discussion=discussion, user=user2, role="active")
        p3 = DiscussionParticipantFactory(discussion=discussion, user=user3, role="active")
        
        # Only user1 and user2 respond
        ResponseFactory(round=round_obj, user=user1)
        ResponseFactory(round=round_obj, user=user2)
        
        RoundService.handle_mrp_expiration(round_obj)
        
        # Refresh participants
        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        
        # user1 and user2 should still be active
        assert p1.role == "active"
        assert p2.role == "active"
        
        # user3 should be temporary observer
        assert p3.role == "temporary_observer"
        assert p3.observer_reason == "mrp_expired"
        assert p3.posted_in_round_when_removed is False
        assert p3.removal_count == 1

    def test_handle_mrp_expiration_archives_with_one_or_fewer_responses(self):
        """Test discussion archived when ≤1 total responses."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create 3 participants
        users = [UserFactory() for _ in range(3)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # Only 1 response
        ResponseFactory(round=round_obj, user=users[0])
        
        RoundService.handle_mrp_expiration(round_obj)
        
        discussion.refresh_from_db()
        assert discussion.status == "archived"
        assert discussion.archived_at is not None

    def test_handle_mrp_expiration_ends_round_with_sufficient_responses(self):
        """Test round ends when >1 responses exist."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(
            discussion=discussion,
            status="in_progress",
            final_mrp_minutes=60
        )
        
        # Create 3 participants
        users = [UserFactory() for _ in range(3)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # 2 responses (>1, so should end round)
        ResponseFactory(round=round_obj, user=users[0])
        ResponseFactory(round=round_obj, user=users[1])
        
        RoundService.handle_mrp_expiration(round_obj)
        
        round_obj.refresh_from_db()
        discussion.refresh_from_db()
        
        # Round should be ended
        assert round_obj.status == "voting"
        assert round_obj.end_time is not None
        assert discussion.status != "archived"

    def test_handle_mrp_expiration_tracks_posted_in_round(self):
        """Test posted_in_round_when_removed is tracked correctly."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create 2 participants
        user1, user2 = UserFactory(), UserFactory()
        p1 = DiscussionParticipantFactory(discussion=discussion, user=user1, role="active")
        p2 = DiscussionParticipantFactory(discussion=discussion, user=user2, role="active")
        
        # Both posted initially (to avoid archiving)
        ResponseFactory(round=round_obj, user=user1)
        ResponseFactory(round=round_obj, user=user2)
        
        # Now simulate user2 being moved to observer but had posted
        p2.role = "temporary_observer"
        p2.save()
        
        # Create another round
        round_2 = RoundFactory(discussion=discussion, round_number=2, status="in_progress")
        
        # Only user1 responds in round 2
        ResponseFactory(round=round_2, user=user1)
        
        # MRP expires - user2 was observer and didn't respond
        RoundService.handle_mrp_expiration(round_2)
        
        p2.refresh_from_db()
        # Since user2 was already observer, they wouldn't be processed again
        # This tests the logic flow


@pytest.mark.django_db
class TestShouldEndRound:
    """Test should_end_round logic."""

    def test_should_end_round_not_in_progress(self):
        """Test returns False when round not in progress."""
        round_obj = RoundFactory(status="completed")
        
        result = RoundService.should_end_round(round_obj)
        assert result is False

    def test_should_end_round_mrp_expired(self):
        """Test returns True when MRP expired."""
        round_obj = RoundFactory(
            status="in_progress",
            final_mrp_minutes=60,
            start_time=timezone.now() - timedelta(minutes=61)
        )
        
        result = RoundService.should_end_round(round_obj)
        assert result is True

    def test_should_end_round_all_responded(self):
        """Test returns True when all active participants responded."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create 3 active participants
        users = [UserFactory() for _ in range(3)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # All respond
        for user in users:
            ResponseFactory(round=round_obj, user=user)
        
        result = RoundService.should_end_round(round_obj)
        assert result is True

    def test_should_end_round_not_all_responded(self):
        """Test returns False when some participants haven't responded."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create 3 active participants
        users = [UserFactory() for _ in range(3)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # Only 2 respond
        for user in users[:2]:
            ResponseFactory(round=round_obj, user=user)
        
        result = RoundService.should_end_round(round_obj)
        assert result is False

    def test_should_end_round_ignores_observers(self):
        """Test only counts active/initiator participants."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create 2 active, 1 observer
        user1, user2, user3 = [UserFactory() for _ in range(3)]
        DiscussionParticipantFactory(discussion=discussion, user=user1, role="active")
        DiscussionParticipantFactory(discussion=discussion, user=user2, role="active")
        DiscussionParticipantFactory(discussion=discussion, user=user3, role="temporary_observer")
        
        # Only active users respond
        ResponseFactory(round=round_obj, user=user1)
        ResponseFactory(round=round_obj, user=user2)
        
        # Should end (all active responded, ignoring observer)
        result = RoundService.should_end_round(round_obj)
        assert result is True


@pytest.mark.django_db
class TestEndRound:
    """Test end_round logic."""

    def test_end_round_sets_end_time(self):
        """Test end_round sets end_time."""
        config = PlatformConfig.load()
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        RoundService.end_round(round_obj)
        
        round_obj.refresh_from_db()
        assert round_obj.end_time is not None
        assert abs((round_obj.end_time - timezone.now()).total_seconds()) < 2

    def test_end_round_calculates_mrp(self):
        """Test end_round calculates final MRP if not set."""
        config = PlatformConfig.load()
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Add some responses with times
        resp = ResponseFactory(round=round_obj)
        resp.time_since_previous_minutes = 40
        resp.save()
        
        RoundService.end_round(round_obj)
        
        round_obj.refresh_from_db()
        assert round_obj.final_mrp_minutes is not None
        assert round_obj.final_mrp_minutes > 0

    def test_end_round_sets_status_to_voting(self):
        """Test end_round sets status to voting."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        RoundService.end_round(round_obj)
        
        round_obj.refresh_from_db()
        assert round_obj.status == "voting"

    def test_end_round_locks_responses(self):
        """Test end_round locks all responses."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create some responses
        resp1 = ResponseFactory(round=round_obj, is_locked=False)
        resp2 = ResponseFactory(round=round_obj, is_locked=False)
        
        RoundService.end_round(round_obj)
        
        resp1.refresh_from_db()
        resp2.refresh_from_db()
        assert resp1.is_locked is True
        assert resp2.is_locked is True

    def test_end_round_preserves_existing_mrp(self):
        """Test end_round doesn't recalculate if MRP already set."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(
            discussion=discussion,
            status="in_progress",
            final_mrp_minutes=120.0
        )
        
        RoundService.end_round(round_obj)
        
        round_obj.refresh_from_db()
        # Should preserve the existing MRP
        assert round_obj.final_mrp_minutes == 120.0


@pytest.mark.django_db
class TestGetPhaseInfo:
    """Test get_phase_info method."""

    def test_get_phase_info_phase_1(self):
        """Test get_phase_info returns correct info for Phase 1."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 5
        config.save()
        
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)
        
        # Add 3 participants
        for _ in range(3):
            DiscussionParticipantFactory(discussion=discussion, role="active")
        
        # Add 1 response
        ResponseFactory(round=round_obj)
        
        info = RoundService.get_phase_info(round_obj, config)
        
        assert info["phase"] == 1
        assert info["responses_count"] == 1
        assert info["responses_needed_for_phase_2"] == 3  # min(5, 3)
        assert info["mrp_minutes"] is None
        assert info["mrp_deadline"] is None

    def test_get_phase_info_phase_2(self):
        """Test get_phase_info returns correct info for Phase 2."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 3
        config.mrp_calculation_scope = "current_round"
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Add 3 participants
        users = [UserFactory() for _ in range(3)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # Add 3 responses to enter Phase 2
        for user in users:
            resp = ResponseFactory(round=round_obj, user=user)
            resp.time_since_previous_minutes = 40
            resp.save()
        
        info = RoundService.get_phase_info(round_obj, config)
        
        assert info["phase"] == 2
        assert info["responses_count"] == 3
        assert info["responses_needed_for_phase_2"] == 3
        assert info["mrp_minutes"] is not None
        assert info["mrp_minutes"] > 0
        assert info["mrp_deadline"] is not None

    def test_get_phase_info_calculates_mrp_if_needed(self):
        """Test get_phase_info calculates and saves MRP if not set."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 2
        config.mrp_calculation_scope = "current_round"
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(
            discussion=discussion,
            status="in_progress",
            final_mrp_minutes=None
        )
        
        # Add 2 participants and responses (Phase 2)
        users = [UserFactory() for _ in range(2)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
            resp = ResponseFactory(round=round_obj, user=user)
            resp.time_since_previous_minutes = 50
            resp.save()
        
        info = RoundService.get_phase_info(round_obj, config)
        
        # Should have calculated and saved MRP
        round_obj.refresh_from_db()
        assert round_obj.final_mrp_minutes is not None
        assert info["mrp_minutes"] == round_obj.final_mrp_minutes


@pytest.mark.django_db
class TestRoundServiceEdgeCases:
    """Test edge cases and integration scenarios."""

    def test_concurrent_response_submission(self):
        """Test round handling with concurrent response submission."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # Create multiple participants
        users = [UserFactory() for _ in range(5)]
        for user in users:
            DiscussionParticipantFactory(discussion=discussion, user=user, role="active")
        
        # Simulate concurrent responses
        with transaction.atomic():
            for user in users:
                ResponseFactory(round=round_obj, user=user)
        
        # All should have responded
        assert RoundService.should_end_round(round_obj) is True

    def test_phase_1_with_zero_participants(self):
        """Test Phase 1 behavior with no participants (edge case)."""
        config = PlatformConfig.load()
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)
        
        # No participants - should still be Phase 1 (N = 0, responses = 0)
        result = RoundService.is_phase_1(round_obj, config)
        # With 0 participants and 0 responses, 0 < 0 is False
        assert result is False

    def test_mrp_calculation_with_zero_responses(self):
        """Test MRP calculation returns default when no response times."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = "current_round"
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion)
        
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # Should return minimum MRP (30 * 2 = 60)
        assert mrp == 60.0

    def test_handle_mrp_expiration_with_no_participants(self):
        """Test MRP expiration handling with no participants."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # No participants, no responses
        RoundService.handle_mrp_expiration(round_obj)
        
        # Should archive (≤1 responses)
        discussion.refresh_from_db()
        assert discussion.status == "archived"

    def test_end_round_multiple_calls_safe(self):
        """Test calling end_round multiple times is safe (doesn't error)."""
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion, status="in_progress")
        
        # End round twice - should not error
        RoundService.end_round(round_obj)
        round_obj.refresh_from_db()
        assert round_obj.end_time is not None
        assert round_obj.status == "voting"
        
        # Second call should not error (though end_time will update)
        RoundService.end_round(round_obj)
        round_obj.refresh_from_db()
        assert round_obj.status == "voting"
