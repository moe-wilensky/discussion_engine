"""
Tests for discussion termination conditions.

Tests all termination conditions and archival logic.
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


@pytest.mark.django_db
class TestTerminationConditions:
    """Test discussion termination and archival"""

    @pytest.fixture
    def setup_termination_scenario(self):
        """Create discussion for termination testing"""
        config = PlatformConfig.load()

        # Create users
        users = []
        for i in range(3):
            user = User.objects.create_user(
                username=f"user{i}", phone_number=f"+1123456789{i}", password="test123"
            )
            users.append(user)

        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline="Termination Test",
            topic_details="Testing termination",
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

        return {"config": config, "users": users, "discussion": discussion}

    def test_archive_when_one_or_fewer_responses(self, setup_termination_scenario):
        """Archive when round receives ≤1 response"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Create round with only 1 response
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        Response.objects.create(
            round=round,
            user=data["users"][0],
            content="Only response",
            character_count=13,
        )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round, config
        )

        assert should_archive is True
        assert "only 1 response" in reason.lower()

    def test_archive_when_zero_responses(self, setup_termination_scenario):
        """Archive when round receives 0 responses"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        # No responses
        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round, config
        )

        assert should_archive is True
        assert "0 response" in reason.lower()

    def test_archive_when_max_duration_reached(self, setup_termination_scenario):
        """Archive when max_discussion_duration_days reached"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Set max duration to 7 days
        config.max_discussion_duration_days = 7
        config.save()

        # Make discussion 8 days old
        discussion.created_at = timezone.now() - timedelta(days=8)
        discussion.save()

        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        # Add enough responses to not trigger response count check
        for user in data["users"]:
            Response.objects.create(
                round=round, user=user, content="Response", character_count=8
            )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round, config
        )

        assert should_archive is True
        assert "duration" in reason.lower()

    def test_archive_when_max_rounds_reached(self, setup_termination_scenario):
        """Archive when max_discussion_rounds reached"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Set max rounds to 5
        config.max_discussion_rounds = 5
        config.save()

        # Create round 5
        round5 = Round.objects.create(
            discussion=discussion,
            round_number=5,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        # Add responses
        for user in data["users"]:
            Response.objects.create(
                round=round5, user=user, content="Response", character_count=8
            )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round5, config
        )

        assert should_archive is True
        assert "maximum rounds" in reason.lower()

    def test_archive_when_max_responses_reached(self, setup_termination_scenario):
        """Archive when max_discussion_responses reached"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Set max total responses to 10
        config.max_discussion_responses = 10
        config.save()

        # Create multiple rounds with responses
        for round_num in range(1, 4):
            round = Round.objects.create(
                discussion=discussion,
                round_number=round_num,
                status="completed" if round_num < 3 else "in_progress",
                final_mrp_minutes=60.0,
            )

            # Add 3-4 responses per round
            for user in data["users"]:
                Response.objects.create(
                    round=round, user=user, content="Response" * 10, character_count=80
                )

        # Total: 9 responses
        # Add 2 more to exceed limit
        current_round = Round.objects.get(discussion=discussion, round_number=3)
        Response.objects.create(
            round=current_round,
            user=data["users"][0],
            content="Extra",
            character_count=5,
        )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, current_round, config
        )

        assert should_archive is True
        assert "maximum responses" in reason.lower()

    def test_archive_when_all_participants_permanent_observers(
        self, setup_termination_scenario
    ):
        """Archive when all active participants become permanent observers"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Make all participants permanent observers
        DiscussionParticipant.objects.filter(discussion=discussion).update(
            role="permanent_observer"
        )

        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round, config
        )

        assert should_archive is True
        assert "permanent observers" in reason.lower()

    def test_archival_process(self, setup_termination_scenario):
        """Test archival process sets correct fields"""
        data = setup_termination_scenario
        discussion = data["discussion"]

        # Create some responses
        round = Round.objects.create(
            discussion=discussion, round_number=1, final_mrp_minutes=60.0
        )

        for user in data["users"]:
            Response.objects.create(
                round=round, user=user, content="Test", character_count=4
            )

        MultiRoundService.archive_discussion(discussion, "Test archival reason")

        discussion.refresh_from_db()

        assert discussion.status == "archived"
        assert discussion.archived_at is not None
        assert discussion.archived_at <= timezone.now()

    def test_all_responses_locked_on_archive(self, setup_termination_scenario):
        """All responses locked when discussion archived"""
        data = setup_termination_scenario
        discussion = data["discussion"]

        # Create multiple rounds with responses
        for round_num in range(1, 3):
            round = Round.objects.create(
                discussion=discussion, round_number=round_num, final_mrp_minutes=60.0
            )

            for user in data["users"]:
                Response.objects.create(
                    round=round,
                    user=user,
                    content="Response",
                    character_count=8,
                    is_locked=False,
                )

        # Archive discussion
        MultiRoundService.archive_discussion(discussion, "Test")

        # All responses should be locked
        unlocked_count = Response.objects.filter(
            round__discussion=discussion, is_locked=False
        ).count()

        assert unlocked_count == 0

    def test_termination_conditions_checked_in_order(self, setup_termination_scenario):
        """Termination conditions checked in order, first match triggers"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Set up multiple termination conditions
        config.max_discussion_rounds = 10
        config.max_discussion_duration_days = 30
        config.save()

        # Create round with only 1 response (first condition)
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        Response.objects.create(
            round=round, user=data["users"][0], content="Only one", character_count=8
        )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round, config
        )

        # Should archive due to first condition (≤1 response)
        assert should_archive is True
        assert "response" in reason.lower()

    def test_no_archive_when_conditions_not_met(self, setup_termination_scenario):
        """Discussion continues when no termination conditions met"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Set high limits
        config.max_discussion_rounds = 100
        config.max_discussion_duration_days = 365
        config.max_discussion_responses = 1000
        config.save()

        # Create round with enough responses
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        for user in data["users"]:
            Response.objects.create(
                round=round, user=user, content="Response", character_count=8
            )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round, config
        )

        assert should_archive is False
        assert reason is None

    def test_config_zero_disables_limit(self, setup_termination_scenario):
        """Config value of 0 disables that limit"""
        data = setup_termination_scenario
        discussion = data["discussion"]
        config = data["config"]

        # Set limits to 0 (disabled)
        config.max_discussion_rounds = 0
        config.max_discussion_duration_days = 0
        config.max_discussion_responses = 0
        config.save()

        # Create round 100 (would normally trigger if limit was active)
        round = Round.objects.create(
            discussion=discussion,
            round_number=100,
            status="in_progress",
            final_mrp_minutes=60.0,
        )

        # Add enough responses
        for user in data["users"]:
            Response.objects.create(
                round=round, user=user, content="Response", character_count=8
            )

        should_archive, reason = MultiRoundService.check_termination_conditions(
            discussion, round, config
        )

        # Should NOT archive (limits disabled)
        assert should_archive is False
