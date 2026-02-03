"""
Tests for observer reintegration with nuanced rules.

Tests all 5 scenarios for observer status and rejoining.
"""

import pytest
from django.utils import timezone
from datetime import timedelta

from core.models import (
    User, Discussion, Round, DiscussionParticipant,
    PlatformConfig, Response
)
from core.services.observer_service import ObserverService


@pytest.mark.django_db
class TestObserverReintegration:
    """Test nuanced observer reintegration rules"""

    @pytest.fixture
    def setup_observer_scenario(self):
        """Create discussion with rounds for observer testing"""
        config = PlatformConfig.load()
        
        # Create users
        initiator = User.objects.create_user(
            username='initiator',
            phone_number='+11234567890',
            password='test123'
        )
        invitee = User.objects.create_user(
            username='invitee',
            phone_number='+11234567891',
            password='test123'
        )
        active_user = User.objects.create_user(
            username='active',
            phone_number='+11234567892',
            password='test123'
        )
        
        # Create discussion
        discussion = Discussion.objects.create(
            topic_headline='Test Discussion',
            topic_details='Testing observer rules',
            max_response_length_chars=1000,
            response_time_multiplier=1.0,
            min_response_time_minutes=30,
            initiator=initiator
        )
        
        # Create participants
        DiscussionParticipant.objects.create(
            discussion=discussion, user=initiator, role='initiator'
        )
        
        return {
            'config': config,
            'initiator': initiator,
            'invitee': invitee,
            'active_user': active_user,
            'discussion': discussion
        }

    def test_scenario_1_initial_invitee_never_participated(self, setup_observer_scenario):
        """Scenario 1: Initial invitees who never participated can join anytime"""
        data = setup_observer_scenario
        discussion = data['discussion']
        invitee = data['invitee']
        
        # Create participant who never posted
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=invitee,
            role='active'
        )
        
        # Create round
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            final_mrp_minutes=60.0
        )
        
        # User never responded, should be able to join
        can_rejoin, reason = ObserverService.can_rejoin(participant, round)
        
        assert can_rejoin is True
        assert reason == ""

    def test_scenario_2_mutual_removal_before_posting(self, setup_observer_scenario):
        """Scenario 2: Mutual removal BEFORE posting -> can rejoin same round after 1 MRP"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        # Create participant
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='active'
        )
        
        # Create round
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            start_time=timezone.now() - timedelta(hours=2),
            final_mrp_minutes=60.0
        )
        
        # User had posted in a previous round (to distinguish from scenario 1)
        old_round = Round.objects.create(
            discussion=discussion,
            round_number=0,
            status='completed',
            final_mrp_minutes=60.0
        )
        Response.objects.create(
            round=old_round, user=user,
            content='Previous', character_count=8
        )
        
        # Move to observer BEFORE posting in current round
        removal_time = timezone.now() - timedelta(minutes=70)
        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=False
        )
        participant.observer_since = removal_time
        participant.save()
        
        # Should be able to rejoin (1 MRP = 60 min has elapsed)
        can_rejoin, reason = ObserverService.can_rejoin(participant, round)
        
        assert can_rejoin is True

    def test_scenario_2_mutual_removal_before_posting_wait_period(self, setup_observer_scenario):
        """Scenario 2: Must wait 1 MRP before rejoining same round"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='active'
        )
        
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            start_time=timezone.now() - timedelta(hours=2),
            final_mrp_minutes=60.0
        )
        
        # Move to observer 30 minutes ago (1 MRP = 60 min not elapsed)
        removal_time = timezone.now() - timedelta(minutes=30)
        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=False
        )
        participant.observer_since = removal_time
        participant.save()
        
        # Should NOT be able to rejoin yet
        can_rejoin, reason = ObserverService.can_rejoin(participant, round)
        
        assert can_rejoin is False
        assert 'wait' in reason

    def test_scenario_3_mutual_removal_after_posting(self, setup_observer_scenario):
        """Scenario 3: Mutual removal AFTER posting -> must wait until 1 MRP in NEXT round"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='active'
        )
        
        # Round 1 where removal occurred
        round1 = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='completed',
            start_time=timezone.now() - timedelta(hours=3),
            final_mrp_minutes=60.0
        )
        
        # User posted in round 1
        Response.objects.create(
            round=round1, user=user,
            content='Posted', character_count=6
        )
        
        # Move to observer AFTER posting
        removal_time = timezone.now() - timedelta(hours=2)
        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=True
        )
        participant.observer_since = removal_time
        participant.save()
        
        # Round 2 started recently (less than 1 MRP ago)
        round2 = Round.objects.create(
            discussion=discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now() - timedelta(minutes=30),
            final_mrp_minutes=60.0
        )
        
        # Should NOT be able to rejoin yet (1 MRP not elapsed in round 2)
        can_rejoin, reason = ObserverService.can_rejoin(participant, round2)
        
        # Since 1 MRP hasn't elapsed in round 2, can't rejoin yet
        assert can_rejoin is False

    def test_scenario_3_must_wait_for_next_round(self, setup_observer_scenario):
        """Scenario 3: Cannot rejoin same round if removed after posting"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='active'
        )
        
        round1 = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            start_time=timezone.now() - timedelta(hours=2),
            final_mrp_minutes=60.0
        )
        
        # User posted in round 1
        Response.objects.create(
            round=round1, user=user,
            content='Posted', character_count=6
        )
        
        # Move to observer AFTER posting (30 min ago)
        removal_time = timezone.now() - timedelta(minutes=30)
        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=True
        )
        participant.observer_since = removal_time
        participant.save()
        
        # Still in round 1 - should NOT be able to rejoin
        can_rejoin, reason = ObserverService.can_rejoin(participant, round1)
        
        assert can_rejoin is False
        assert 'wait_for_next_round' in reason

    def test_scenario_4_mrp_expiration(self, setup_observer_scenario):
        """Scenario 4: MRP expiration -> must wait until 1 MRP in NEXT round"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='active'
        )
        
        # Round 1 where MRP expired
        round1 = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='completed',
            start_time=timezone.now() - timedelta(hours=3),
            final_mrp_minutes=60.0
        )
        
        # Move to observer due to MRP expiration (user didn't post)
        removal_time = timezone.now() - timedelta(hours=2)
        ObserverService.move_to_observer(
            participant,
            reason='mrp_expired',
            posted_in_round=False
        )
        participant.observer_since = removal_time
        participant.save()
        
        # Round 2 started recently (less than 1 MRP ago)
        round2 = Round.objects.create(
            discussion=discussion,
            round_number=2,
            status='in_progress',
            start_time=timezone.now() - timedelta(minutes=30),
            final_mrp_minutes=60.0
        )
        
        # Should NOT be able to rejoin yet (1 MRP not elapsed in round 2)
        can_rejoin, reason = ObserverService.can_rejoin(participant, round2)
        
        assert can_rejoin is False

    def test_scenario_5_permanent_observer(self, setup_observer_scenario):
        """Scenario 5: Permanent observer -> never rejoin"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='permanent_observer',
            observer_reason='vote_based_removal'
        )
        
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            final_mrp_minutes=60.0
        )
        
        # Should NEVER be able to rejoin
        can_rejoin, reason = ObserverService.can_rejoin(participant, round)
        
        assert can_rejoin is False
        assert reason == 'permanent'

    def test_wait_period_calculation(self, setup_observer_scenario):
        """Test wait period calculation is correct"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='temporary_observer',
            observer_reason='mutual_removal',
            posted_in_round_when_removed=False
        )
        
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            start_time=timezone.now() - timedelta(hours=1),
            final_mrp_minutes=60.0
        )
        
        removal_time = timezone.now() - timedelta(minutes=30)
        participant.observer_since = removal_time
        participant.save()
        
        wait_end = ObserverService.get_wait_period_end(participant, round)
        
        # Should be removal_time + 60 minutes (1 MRP)
        expected_end = removal_time + timedelta(minutes=60)
        
        # Allow for reasonable calculation time
        assert wait_end is not None
        assert abs((wait_end - expected_end).total_seconds()) < 10

    def test_rejoin_at_correct_time(self, setup_observer_scenario):
        """Test rejoining is allowed at correct time"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='temporary_observer',
            observer_reason='mutual_removal',
            posted_in_round_when_removed=False
        )
        
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            start_time=timezone.now() - timedelta(hours=2),
            final_mrp_minutes=60.0
        )
        
        # Set removal time 61 minutes ago (just past 1 MRP)
        participant.observer_since = timezone.now() - timedelta(minutes=61)
        participant.save()
        
        # Should be able to rejoin
        ObserverService.rejoin_as_active(participant)
        
        participant.refresh_from_db()
        assert participant.role == 'active'
        assert participant.observer_since is None
        assert participant.observer_reason is None

    def test_rejoin_before_wait_period_rejected(self, setup_observer_scenario):
        """Test rejoining before wait period is rejected"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='temporary_observer',
            observer_reason='mutual_removal',
            posted_in_round_when_removed=False
        )
        
        round = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status='in_progress',
            start_time=timezone.now() - timedelta(hours=1),
            final_mrp_minutes=60.0
        )
        
        # Set removal time 30 minutes ago (before 1 MRP)
        participant.observer_since = timezone.now() - timedelta(minutes=30)
        participant.save()
        
        # Should NOT be able to rejoin
        with pytest.raises(ValueError, match="Cannot rejoin"):
            ObserverService.rejoin_as_active(participant)

    def test_make_permanent_observer(self, setup_observer_scenario):
        """Test making user permanent observer"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        user.platform_invites_acquired = 10
        user.platform_invites_banked = 5
        user.save()
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='active'
        )
        
        ObserverService.make_permanent_observer(
            participant,
            reason='vote_based_removal'
        )
        
        participant.refresh_from_db()
        user.refresh_from_db()
        
        assert participant.role == 'permanent_observer'
        assert participant.observer_reason == 'vote_based_removal'
        assert user.platform_invites_acquired == 0
        assert user.platform_invites_banked == 0

    def test_removal_count_increments(self, setup_observer_scenario):
        """Test removal count increments for mutual removal"""
        data = setup_observer_scenario
        discussion = data['discussion']
        user = data['active_user']
        
        participant = DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user,
            role='active',
            removal_count=0
        )
        
        # First removal
        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=False
        )
        
        assert participant.removal_count == 1
        
        # Rejoin and get removed again
        participant.role = 'active'
        participant.save()
        
        ObserverService.move_to_observer(
            participant,
            reason='mutual_removal',
            posted_in_round=False
        )
        
        assert participant.removal_count == 2
