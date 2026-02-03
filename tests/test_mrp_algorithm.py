"""
Tests for MRP (Median Response Period) calculation algorithm.

Comprehensive tests following the spec Section 5.2 examples.
"""

import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import PlatformConfig
from core.services.round_service import RoundService
from tests.factories import (
    UserFactory, DiscussionFactory, RoundFactory, 
    ResponseFactory, DiscussionParticipantFactory
)


@pytest.mark.django_db
class TestMRPCalculation:
    """Test MRP calculation algorithm."""
    
    def test_mrp_spec_example(self):
        """
        Test exact example from spec:
        Response times: [10, 60, 40]
        MRM = 30, RTM = 2
        Expected: Adjusted [30, 60, 40], Median = 40, MRP = 80
        """
        # Setup
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion)
        
        # Create responses with specific time gaps
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()
        
        resp1 = ResponseFactory(round=round_obj, user=user1)
        resp1.time_since_previous_minutes = 10
        resp1.save()
        
        resp2 = ResponseFactory(round=round_obj, user=user2)
        resp2.time_since_previous_minutes = 60
        resp2.save()
        
        resp3 = ResponseFactory(round=round_obj, user=user3)
        resp3.time_since_previous_minutes = 40
        resp3.save()
        
        # Calculate MRP
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # Expected: [30, 60, 40] -> median 40 -> MRP = 40 * 2 = 80
        assert mrp == 80.0
    
    def test_mrp_dynamic_recalculation(self):
        """
        Test dynamic recalculation example from spec:
        Initial: [10, 60, 40] -> MRP = 80
        After adding t4=20: [30, 60, 40, 30] -> Median = 35 -> MRP = 70
        """
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion)
        
        # Create first 3 responses
        for time in [10, 60, 40]:
            resp = ResponseFactory(round=round_obj)
            resp.time_since_previous_minutes = time
            resp.save()
        
        # Initial MRP
        mrp1 = RoundService.calculate_mrp(round_obj, config)
        assert mrp1 == 80.0
        
        # Add 4th response
        resp4 = ResponseFactory(round=round_obj)
        resp4.time_since_previous_minutes = 20
        resp4.save()
        
        # Recalculate
        mrp2 = RoundService.calculate_mrp(round_obj, config)
        
        # Expected: [30, 60, 40, 30] -> median 35 -> MRP = 70
        assert mrp2 == 70.0
    
    def test_minimum_mrp(self):
        """Test that MRP is clamped to MRM * RTM minimum."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion)
        
        # Create responses all below MRM
        for time in [5, 10, 15]:
            resp = ResponseFactory(round=round_obj)
            resp.time_since_previous_minutes = time
            resp.save()
        
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # All times become MRM (30), median = 30, MRP = 60
        # But minimum MRP = MRM * RTM = 30 * 2 = 60
        assert mrp == 60.0
    
    def test_median_even_number_of_times(self):
        """Test median calculation with even number of values."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=10,
            response_time_multiplier=1.5
        )
        round_obj = RoundFactory(discussion=discussion)
        
        # Create 4 responses: [40, 50, 60, 70]
        for time in [40, 50, 60, 70]:
            resp = ResponseFactory(round=round_obj)
            resp.time_since_previous_minutes = time
            resp.save()
        
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # Median of [40, 50, 60, 70] = (50 + 60) / 2 = 55
        # MRP = 55 * 1.5 = 82.5
        assert mrp == 82.5
    
    def test_median_odd_number_of_times(self):
        """Test median calculation with odd number of values."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=10,
            response_time_multiplier=1.5
        )
        round_obj = RoundFactory(discussion=discussion)
        
        # Create 5 responses: [30, 40, 50, 60, 70]
        for time in [30, 40, 50, 60, 70]:
            resp = ResponseFactory(round=round_obj)
            resp.time_since_previous_minutes = time
            resp.save()
        
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # Median = 50, MRP = 50 * 1.5 = 75
        assert mrp == 75.0
    
    def test_all_times_below_mrm(self):
        """Test that all times below MRM are adjusted to MRM."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=100,
            response_time_multiplier=1.5
        )
        round_obj = RoundFactory(discussion=discussion)
        
        # All times below MRM
        for time in [10, 20, 30, 40, 50]:
            resp = ResponseFactory(round=round_obj)
            resp.time_since_previous_minutes = time
            resp.save()
        
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # All become 100, median = 100, MRP = 150
        assert mrp == 150.0
    
    def test_large_dataset(self):
        """Test MRP calculation with 100+ responses."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion)
        
        # Create 100 responses with times from 20 to 120
        for i in range(100):
            resp = ResponseFactory(round=round_obj)
            resp.time_since_previous_minutes = 20 + i
            resp.save()
        
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # Times: [30, 31, 32, ..., 119] (first 10 adjusted from 20-29 to 30)
        # With 100 values, median is average of 50th and 51st
        # Should be around 69-70, MRP around 138-140
        assert 130 <= mrp <= 145
    
    def test_no_responses_returns_default(self):
        """Test that MRP returns MRM * RTM when no responses exist."""
        config = PlatformConfig.load()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=30,
            response_time_multiplier=2.0
        )
        round_obj = RoundFactory(discussion=discussion)
        
        mrp = RoundService.calculate_mrp(round_obj, config)
        
        # No responses, should return minimum MRP = MRM * RTM
        assert mrp == 60.0  # 30 * 2.0


@pytest.mark.django_db
class TestMRPScopes:
    """Test MRP calculation with different scope configurations."""
    
    def test_current_round_scope(self):
        """Test MRP calculation using only current round."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'current_round'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=10,
            response_time_multiplier=1.5
        )
        
        # Round 1 with responses
        round1 = RoundFactory(discussion=discussion, round_number=1)
        for time in [100, 200]:
            resp = ResponseFactory(round=round1)
            resp.time_since_previous_minutes = time
            resp.save()
        
        # Round 2 with different responses
        round2 = RoundFactory(discussion=discussion, round_number=2)
        for time in [20, 30]:
            resp = ResponseFactory(round=round2)
            resp.time_since_previous_minutes = time
            resp.save()
        
        # Calculate for round 2 - should only use round 2 data
        mrp = RoundService.calculate_mrp(round2, config)
        
        # Median of [20, 30] = 25, MRP = 37.5
        assert mrp == 37.5
    
    def test_all_rounds_scope(self):
        """Test MRP calculation using all rounds."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'all_rounds'
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=10,
            response_time_multiplier=2.0
        )
        
        # Round 1
        round1 = RoundFactory(discussion=discussion, round_number=1)
        for time in [20, 40]:
            resp = ResponseFactory(round=round1)
            resp.time_since_previous_minutes = time
            resp.save()
        
        # Round 2
        round2 = RoundFactory(discussion=discussion, round_number=2)
        for time in [60, 80]:
            resp = ResponseFactory(round=round2)
            resp.time_since_previous_minutes = time
            resp.save()
        
        # Calculate for round 2 - should use both rounds
        mrp = RoundService.calculate_mrp(round2, config)
        
        # All times: [20, 40, 60, 80]
        # Median = (40 + 60) / 2 = 50
        # MRP = 100
        assert mrp == 100.0
    
    def test_last_x_rounds_scope(self):
        """Test MRP calculation using last X rounds."""
        config = PlatformConfig.load()
        config.mrp_calculation_scope = 'last_X_rounds'
        config.mrp_calculation_x_rounds = 2
        config.save()
        
        discussion = DiscussionFactory(
            min_response_time_minutes=10,
            response_time_multiplier=2.0
        )
        
        # Round 1 (should be excluded - only last 2 rounds)
        round1 = RoundFactory(discussion=discussion, round_number=1)
        resp = ResponseFactory(round=round1)
        resp.time_since_previous_minutes = 100
        resp.save()
        
        # Round 2
        round2 = RoundFactory(discussion=discussion, round_number=2)
        resp = ResponseFactory(round=round2)
        resp.time_since_previous_minutes = 30
        resp.save()
        
        # Round 3
        round3 = RoundFactory(discussion=discussion, round_number=3)
        resp = ResponseFactory(round=round3)
        resp.time_since_previous_minutes = 50
        resp.save()
        
        # Calculate for round 3 - should use rounds 2 and 3
        mrp = RoundService.calculate_mrp(round3, config)
        
        # Times: [30, 50] from rounds 2 and 3
        # Median = 40, MRP = 80
        assert mrp == 80.0
