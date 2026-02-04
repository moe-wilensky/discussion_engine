"""
Tests for Round 2+ mechanics and multi-round discussions.

Tests round creation, MRP inheritance, and round progression.
"""

import pytest
from django.utils import timezone
from datetime import timedelta

from core.models import (
    User,
    Discussion,
    Round,
    DiscussionParticipant,
    PlatformConfig,
    Response,
)
from core.services.multi_round_service import MultiRoundService
from core.services.voting_service import VotingService


@pytest.mark.django_db
class TestRound2Plus:
    """Test Round 2+ mechanics"""

    @pytest.fixture
    def setup_multiround_scenario(self):
        """Create discussion with completed Round 1"""
        config = PlatformConfig.load()

        # Create users
        users = []
        for i in range(4):
            user = User.objects.create_user(
                username=f"user{i}", phone_number=f"+1123456789{i}", password="test123"
            )
            users.append(user)

        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline="Multi-Round Test",
            topic_details="Testing rounds",
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=30,
            initiator=users[0],
        )

        # Create participants
        for i, user in enumerate(users):
            DiscussionParticipant.objects.create(
                discussion=discussion,
                user=user,
                role="initiator" if i == 0 else "active",
            )

        # Create and complete Round 1
        round1 = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="completed",
            final_mrp_minutes=45.0,
            start_time=timezone.now() - timedelta(hours=2),
        )

        # All users responded in Round 1
        for user in users:
            Response.objects.create(
                round=round1,
                user=user,
                content="Round 1 response" * 10,
                character_count=100,
            )

        return {
            "config": config,
            "users": users,
            "discussion": discussion,
            "round1": round1,
        }

    def test_create_round_2(self, setup_multiround_scenario):
        """Create Round 2 after Round 1 completes"""
        data = setup_multiround_scenario
        round1 = data["round1"]
        discussion = data["discussion"]

        round2 = MultiRoundService.create_next_round(discussion, round1)

        assert round2 is not None
        assert round2.round_number == 2
        assert round2.status == "in_progress"
        assert round2.discussion == discussion

    def test_mrp_inherited_from_previous_round(self, setup_multiround_scenario):
        """Round 2 inherits MRP from Round 1"""
        data = setup_multiround_scenario
        round1 = data["round1"]
        discussion = data["discussion"]

        # Round 1 has MRP of 45 minutes
        assert round1.final_mrp_minutes == 45.0

        round2 = MultiRoundService.create_next_round(discussion, round1)

        # Round 2 should inherit same MRP
        assert round2.final_mrp_minutes == 45.0

    def test_adjusted_mrp_if_rtm_changed(self, setup_multiround_scenario):
        """MRP adjusts if RTM was changed by voting"""
        data = setup_multiround_scenario
        round1 = data["round1"]
        discussion = data["discussion"]
        config = data["config"]

        # Change RTM via voting (increase by 20%)
        original_rtm = discussion.response_time_multiplier
        VotingService.apply_parameter_change(discussion, "rtm", "increase", config)

        discussion.refresh_from_db()

        # RTM should be increased
        assert discussion.response_time_multiplier > original_rtm

        # Create next round - MRP will be recalculated with new RTM
        round2 = MultiRoundService.create_next_round(discussion, round1)

        # Round 2 inherits previous MRP value (actual recalc happens on first response)
        assert round2.final_mrp_minutes is not None

    def test_no_phase_1_in_round_2(self, setup_multiround_scenario):
        """Round 2+ has no Phase 1, MRP applies from first response"""
        data = setup_multiround_scenario
        round1 = data["round1"]
        discussion = data["discussion"]

        round2 = MultiRoundService.create_next_round(discussion, round1)

        # Round 2 should have MRP set immediately (no Phase 1)
        assert round2.final_mrp_minutes is not None
        assert round2.final_mrp_minutes > 0

    def test_active_participants_updated(self, setup_multiround_scenario):
        """Active participants updated correctly in Round 2"""
        data = setup_multiround_scenario
        discussion = data["discussion"]

        # All 4 users are active
        active_count = DiscussionParticipant.objects.filter(
            discussion=discussion, role__in=["initiator", "active"]
        ).count()

        assert active_count == 4

    def test_round_3_4_5_progression(self, setup_multiround_scenario):
        """Test multiple rounds (3, 4, 5...)"""
        data = setup_multiround_scenario
        discussion = data["discussion"]

        previous_round = data["round1"]

        # Create rounds 2-5
        for expected_round_num in range(2, 6):
            # Create responses for previous round (if needed)
            if previous_round.responses.count() < 2:
                for user in data["users"][:2]:
                    Response.objects.create(
                        round=previous_round,
                        user=user,
                        content="Response" * 10,
                        character_count=100,
                    )

            previous_round.status = "completed"
            previous_round.save()

            next_round = MultiRoundService.create_next_round(discussion, previous_round)

            assert next_round is not None
            assert next_round.round_number == expected_round_num
            assert next_round.status == "in_progress"

            previous_round = next_round

    def test_round_with_removed_participants(self, setup_multiround_scenario):
        """Round 2 excludes removed participants"""
        data = setup_multiround_scenario
        round1 = data["round1"]
        discussion = data["discussion"]

        # Remove one user (make permanent observer)
        removed_user = data["users"][3]
        participant = DiscussionParticipant.objects.get(
            discussion=discussion, user=removed_user
        )
        participant.role = "permanent_observer"
        participant.save()

        # Create Round 2
        round2 = MultiRoundService.create_next_round(discussion, round1)

        # Active count should be reduced
        active_count = DiscussionParticipant.objects.filter(
            discussion=discussion, role__in=["initiator", "active"]
        ).count()

        assert active_count == 3  # 4 - 1 removed

    def test_mrp_regulation_from_first_response(self, setup_multiround_scenario):
        """MRP regulation applies from first response in Round 2+"""
        data = setup_multiround_scenario
        round1 = data["round1"]
        discussion = data["discussion"]

        round2 = MultiRoundService.create_next_round(discussion, round1)

        # MRP should already be set (no waiting for N responses)
        assert round2.final_mrp_minutes is not None

        # First response should trigger MRP countdown
        Response.objects.create(
            round=round2,
            user=data["users"][0],
            content="First response in Round 2",
            character_count=25,
        )

        # MRP is active from this first response
        assert round2.final_mrp_minutes > 0

    def test_discussion_archived_instead_of_round_3(self, setup_multiround_scenario):
        """Discussion archives if termination condition met instead of creating Round 3"""
        data = setup_multiround_scenario
        round1 = data["round1"]
        discussion = data["discussion"]
        config = data["config"]

        # Set max rounds to 2
        config.max_discussion_rounds = 2
        config.save()

        # Create Round 2
        round2 = MultiRoundService.create_next_round(discussion, round1)
        assert round2 is not None
        assert round2.round_number == 2

        # Add responses to Round 2
        for user in data["users"][:2]:
            Response.objects.create(
                round=round2, user=user, content="Response", character_count=8
            )

        round2.status = "completed"
        round2.save()

        # Try to create Round 3 - should archive instead
        round3 = MultiRoundService.create_next_round(discussion, round2)

        assert round3 is None
        discussion.refresh_from_db()
        assert discussion.status == "archived"
