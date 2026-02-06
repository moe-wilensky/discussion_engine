"""
Tests for Round 1 Phase 1 and Phase 2 mechanics.
"""

import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import PlatformConfig
from core.services.round_service import RoundService
from core.services.response_service import ResponseService
from tests.factories import (
    UserFactory,
    DiscussionFactory,
    RoundFactory,
    DiscussionParticipantFactory,
)


@pytest.mark.django_db
class TestPhase1:
    """Test Round 1 Phase 1 (free-form responses)."""

    def test_is_phase_1_true(self):
        """Test phase 1 detection with < N responses."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 5
        config.save()

        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)

        # Add 3 participants
        for _ in range(3):
            DiscussionParticipantFactory(discussion=discussion, role="active")

        assert RoundService.is_phase_1(round_obj, config) is True

    def test_phase_1_to_phase_2_transition(self):
        """Test transition from Phase 1 to Phase 2."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 3
        config.save()

        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)

        # Add 5 participants
        users = [UserFactory() for _ in range(5)]
        for user in users:
            DiscussionParticipantFactory(
                discussion=discussion, user=user, role="active"
            )

        # Initially in Phase 1
        assert RoundService.is_phase_1(round_obj, config) is True

        # Add 3 responses
        for i in range(3):
            ResponseService.submit_response(users[i], round_obj, "Test response")

        # Now in Phase 2
        round_obj.refresh_from_db()
        assert RoundService.is_phase_1(round_obj, config) is False

    def test_n_adjustment_fewer_participants(self):
        """Test N = min(config, invited) when invited < config."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 10
        config.save()

        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)

        # Add 2 more participants (3 total including initiator from DiscussionFactory)
        users = [UserFactory() for _ in range(2)]
        for user in users:
            DiscussionParticipantFactory(
                discussion=discussion, user=user, role="active"
            )

        # Should be Phase 1
        assert RoundService.is_phase_1(round_obj, config) is True

        # Add 3 responses from all 3 participants
        initiator = discussion.initiator
        ResponseService.submit_response(initiator, round_obj, "Response 0")
        for i, user in enumerate(users):
            ResponseService.submit_response(user, round_obj, f"Response {i+1}")

        # Should now be Phase 2 (N = min(10, 3) = 3)
        round_obj.refresh_from_db()
        assert RoundService.is_phase_1(round_obj, config) is False


@pytest.mark.django_db
class TestPhase2:
    """Test Round 1 Phase 2 (MRP-regulated)."""

    def test_mrp_recalculation_after_response(self):
        """Test MRP is recalculated after each Phase 2 response."""
        config = PlatformConfig.load()
        config.n_responses_before_mrp = 2
        config.mrp_calculation_scope = "current_round"
        config.save()

        discussion = DiscussionFactory(
            min_response_time_minutes=30, response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion)

        users = [UserFactory() for _ in range(4)]
        for user in users:
            DiscussionParticipantFactory(
                discussion=discussion, user=user, role="active"
            )

        # First 2 responses to enter Phase 2
        resp1 = ResponseService.submit_response(users[0], round_obj, "First")
        resp1.time_since_previous_minutes = 40
        resp1.save()

        resp2 = ResponseService.submit_response(users[1], round_obj, "Second")
        resp2.time_since_previous_minutes = 60
        resp2.save()

        round_obj.refresh_from_db()
        mrp1 = round_obj.final_mrp_minutes

        # Add 3rd response
        resp3 = ResponseService.submit_response(users[2], round_obj, "Third")
        resp3.time_since_previous_minutes = 50
        resp3.save()

        round_obj.refresh_from_db()
        mrp2 = round_obj.final_mrp_minutes

        # MRP should have changed
        assert mrp1 != mrp2
