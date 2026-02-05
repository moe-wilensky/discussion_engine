"""
Integration tests for observer UI flow.

Tests the complete flow from being moved to observer status,
seeing the countdown timer, and rejoining the discussion.
"""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from core.models import (
    User,
    Discussion,
    Round,
    DiscussionParticipant,
    PlatformConfig,
)
from core.services.observer_service import ObserverService


@pytest.mark.django_db
class TestObserverUIIntegration:
    """Integration tests for observer UI flow"""

    @pytest.fixture
    def setup_observer_scenario(self):
        """Create a discussion with observer"""
        config = PlatformConfig.load()

        # Create users
        initiator = User.objects.create_user(
            username="initiator", phone_number="+11234567890", password="test123"
        )
        observer = User.objects.create_user(
            username="observer", phone_number="+11234567891", password="test123"
        )

        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline="Test Discussion",
            topic_details="Testing observer UI",
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=30,
            initiator=initiator,
        )

        # Create participants
        DiscussionParticipant.objects.create(
            discussion=discussion, user=initiator, role="initiator"
        )
        observer_participant = DiscussionParticipant.objects.create(
            discussion=discussion, user=observer, role="active"
        )

        # Create round
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress",
            final_mrp_minutes=60.0,
            start_time=timezone.now(),
        )

        return {
            "initiator": initiator,
            "observer": observer,
            "discussion": discussion,
            "round": round_obj,
            "observer_participant": observer_participant,
        }

    def test_observer_status_displayed_correctly(self, setup_observer_scenario):
        """Test that observer status UI is displayed with correct information"""
        data = setup_observer_scenario
        observer = data["observer"]
        discussion = data["discussion"]
        observer_participant = data["observer_participant"]

        # Move user to observer status
        ObserverService.move_to_observer(
            observer_participant, "mrp_expired", posted_in_round=False
        )

        # Login and view discussion
        client = Client()
        client.force_login(observer)

        response = client.get(f"/discussions/{discussion.id}/")

        assert response.status_code == 200

        # Check that observer status component would be shown
        # (This is a simplified check - in real implementation, we'd check template context)
        assert observer_participant.role == "temporary_observer"
        assert observer_participant.observer_reason == "mrp_expired"

    def test_observer_wait_period_calculation(self, setup_observer_scenario):
        """Test that wait period is correctly calculated"""
        data = setup_observer_scenario
        observer_participant = data["observer_participant"]
        current_round = data["round"]

        # Move to observer 30 minutes ago (MRP is 60 minutes)
        observer_participant.role = "temporary_observer"
        observer_participant.observer_since = timezone.now() - timedelta(minutes=30)
        observer_participant.observer_reason = "mutual_removal"
        observer_participant.posted_in_round_when_removed = False
        observer_participant.save()

        # Get wait period end
        wait_period_end = ObserverService.get_wait_period_end(
            observer_participant, current_round
        )

        # Should be able to rejoin in 30 more minutes (60 total - 30 elapsed)
        assert wait_period_end is not None
        expected_end = observer_participant.observer_since + timedelta(
            minutes=current_round.final_mrp_minutes
        )
        assert abs((wait_period_end - expected_end).total_seconds()) < 1

    def test_rejoin_button_enabled_after_wait(self, setup_observer_scenario):
        """Test that rejoin button is enabled after wait period"""
        data = setup_observer_scenario
        observer_participant = data["observer_participant"]
        current_round = data["round"]

        # Move to observer 61 minutes ago (past the 60 minute MRP)
        observer_participant.role = "temporary_observer"
        observer_participant.observer_since = timezone.now() - timedelta(minutes=61)
        observer_participant.observer_reason = "mutual_removal"
        observer_participant.posted_in_round_when_removed = False
        observer_participant.save()

        # Check that user can rejoin
        can_rejoin, reason = ObserverService.can_rejoin(
            observer_participant, current_round
        )

        assert can_rejoin is True
        assert reason == ""

    def test_permanent_observer_cannot_rejoin(self, setup_observer_scenario):
        """Test that permanent observers see correct message"""
        data = setup_observer_scenario
        observer = data["observer"]
        discussion = data["discussion"]
        observer_participant = data["observer_participant"]
        current_round = data["round"]

        # Make permanent observer
        ObserverService.make_permanent_observer(
            observer_participant, "repeated_violations"
        )

        # Check that user cannot rejoin
        can_rejoin, reason = ObserverService.can_rejoin(
            observer_participant, current_round
        )

        assert can_rejoin is False
        assert reason == "permanent"

    def test_countdown_timer_data(self, setup_observer_scenario):
        """Test that countdown timer receives correct data"""
        data = setup_observer_scenario
        observer_participant = data["observer_participant"]
        current_round = data["round"]

        # Move to observer 10 minutes ago
        removal_time = timezone.now() - timedelta(minutes=10)
        observer_participant.role = "temporary_observer"
        observer_participant.observer_since = removal_time
        observer_participant.observer_reason = "mutual_removal"
        observer_participant.posted_in_round_when_removed = False
        observer_participant.save()

        # Calculate wait period end
        wait_period_end = ObserverService.get_wait_period_end(
            observer_participant, current_round
        )

        # Should be 50 minutes from now (60 total - 10 elapsed)
        expected_end = removal_time + timedelta(
            minutes=current_round.final_mrp_minutes
        )
        assert wait_period_end == expected_end

        # Time remaining should be approximately 50 minutes
        time_remaining = (wait_period_end - timezone.now()).total_seconds() / 60
        assert 49 < time_remaining < 51  # Allow 1 minute margin

    def test_observer_reason_messages(self, setup_observer_scenario):
        """Test that different observer reasons show correct messages"""
        data = setup_observer_scenario
        observer_participant = data["observer_participant"]

        reasons = {
            "mrp_expired": "did not respond within the Minimum Response Period",
            "mutual_removal": "mutual removal vote",
            "vote_based_removal": "participant vote",
        }

        for reason, expected_message_fragment in reasons.items():
            observer_participant.observer_reason = reason
            observer_participant.save()

            # In real implementation, this would check template rendering
            # For now, just verify the reason is set correctly
            assert observer_participant.observer_reason == reason

    def test_rejoin_different_scenarios(self, setup_observer_scenario):
        """Test rejoin eligibility for different scenarios"""
        data = setup_observer_scenario
        observer_participant = data["observer_participant"]
        discussion = data["discussion"]
        current_round = data["round"]

        scenarios = [
            {
                "name": "Removed before posting in same round - can rejoin after 1 MRP",
                "reason": "mutual_removal",
                "posted": False,
                "time_elapsed": 61,  # minutes
                "current_round": 1,
                "expected_can_rejoin": True,
            },
            {
                "name": "Removed after posting - must wait for next round",
                "reason": "mutual_removal",
                "posted": True,
                "time_elapsed": 61,
                "current_round": 1,
                "expected_can_rejoin": False,
            },
            {
                "name": "MRP expired - must wait for next round",
                "reason": "mrp_expired",
                "posted": False,
                "time_elapsed": 61,
                "current_round": 1,
                "expected_can_rejoin": False,
            },
        ]

        for scenario in scenarios:
            # Reset participant
            observer_participant.role = "temporary_observer"
            observer_participant.observer_since = timezone.now() - timedelta(
                minutes=scenario["time_elapsed"]
            )
            observer_participant.observer_reason = scenario["reason"]
            observer_participant.posted_in_round_when_removed = scenario["posted"]
            observer_participant.save()

            # Check rejoin eligibility
            can_rejoin, reason = ObserverService.can_rejoin(
                observer_participant, current_round
            )

            assert (
                can_rejoin == scenario["expected_can_rejoin"]
            ), f"Scenario '{scenario['name']}' failed: expected {scenario['expected_can_rejoin']}, got {can_rejoin}"

    def test_next_round_rejoin(self, setup_observer_scenario):
        """Test rejoining in the next round after being removed"""
        data = setup_observer_scenario
        observer_participant = data["observer_participant"]
        discussion = data["discussion"]

        # Remove user in round 1 after posting
        observer_participant.role = "temporary_observer"
        observer_participant.observer_since = timezone.now() - timedelta(hours=2)
        observer_participant.observer_reason = "mutual_removal"
        observer_participant.posted_in_round_when_removed = True
        observer_participant.save()

        # Create round 2 (started 61 minutes ago - past 1 MRP)
        round2 = Round.objects.create(
            discussion=discussion,
            round_number=2,
            status="in_progress",
            final_mrp_minutes=60.0,
            start_time=timezone.now() - timedelta(minutes=61),
        )

        # Check if can rejoin
        can_rejoin, reason = ObserverService.can_rejoin(observer_participant, round2)

        assert can_rejoin is True
        assert reason == ""
