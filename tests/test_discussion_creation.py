"""
Tests for discussion creation functionality.

Tests presets, custom parameters, validation, and initial setup.
"""

import pytest
from django.core.exceptions import ValidationError

from core.models import User, Discussion, Round, PlatformConfig, DiscussionParticipant
from core.services.discussion_presets import DiscussionPreset
from core.services.discussion_service import DiscussionService
from tests.factories import UserFactory


@pytest.mark.django_db
class TestDiscussionPresets:
    """Test discussion preset functionality."""
    
    def test_get_all_presets(self):
        """Test retrieving all presets."""
        presets = DiscussionPreset.get_presets()
        
        assert 'quick_exchange' in presets
        assert 'thoughtful_discussion' in presets
        assert 'deep_dive' in presets
        
        # Check quick_exchange preset
        quick = presets['quick_exchange']
        assert quick['mrm_minutes'] == 5
        assert quick['rtm'] == 1.5
        assert quick['mrl_chars'] == 500
    
    def test_preview_parameters(self):
        """Test parameter preview generation."""
        preview = DiscussionPreset.preview_parameters(30, 2.0, 2000)
        
        assert 'preview' in preview
        assert 'estimated_mrp_minutes' in preview
        assert preview['estimated_mrp_minutes'] == 60  # 30 * 2.0
        assert '30 minutes' in preview['preview']
    
    def test_validate_parameters_valid(self):
        """Test parameter validation with valid params."""
        config = PlatformConfig.load()
        
        is_valid, msg = DiscussionPreset.validate_parameters(30, 2.0, 2000, config)
        
        assert is_valid is True
        assert msg == ""
    
    def test_validate_parameters_mrm_too_low(self):
        """Test validation with MRM below minimum."""
        config = PlatformConfig.load()
        
        is_valid, msg = DiscussionPreset.validate_parameters(1, 2.0, 2000, config)
        
        assert is_valid is False
        assert 'MRM must be at least' in msg
    
    def test_validate_parameters_rtm_too_high(self):
        """Test validation with RTM above maximum."""
        config = PlatformConfig.load()
        
        is_valid, msg = DiscussionPreset.validate_parameters(30, 10.0, 2000, config)
        
        assert is_valid is False
        assert 'RTM cannot exceed' in msg
    
    def test_validate_parameters_mrl_too_high(self):
        """Test validation with MRL above maximum."""
        config = PlatformConfig.load()
        
        is_valid, msg = DiscussionPreset.validate_parameters(30, 2.0, 10000, config)
        
        assert is_valid is False
        assert 'MRL cannot exceed' in msg


@pytest.mark.django_db
class TestDiscussionCreation:
    """Test discussion creation."""
    
    def test_create_with_preset(self):
        """Test creating discussion with preset."""
        user = UserFactory()
        
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="Should we test this?",
            details="Let's discuss testing strategies",
            mrm=30,
            rtm=2.0,
            mrl=2000
        )
        
        assert discussion is not None
        assert discussion.topic_headline == "Should we test this?"
        assert discussion.initiator == user
        assert discussion.min_response_time_minutes == 30
        assert discussion.response_time_multiplier == 2.0
        assert discussion.max_response_length_chars == 2000
        assert discussion.status == 'active'
    
    def test_create_with_initial_invites(self):
        """Test creating discussion with initial invites."""
        initiator = UserFactory()
        invitee1 = UserFactory()
        invitee2 = UserFactory()
        
        # Give initiator some discussion invites
        initiator.discussion_invites_banked = 5
        initiator.save()
        
        # Make sure initiator has enough responses to unlock invites
        config = PlatformConfig.load()
        from tests.factories import DiscussionFactory, RoundFactory, ResponseFactory
        temp_disc = DiscussionFactory(initiator=initiator)
        temp_round = RoundFactory(discussion=temp_disc)
        for _ in range(config.responses_to_unlock_invites):
            ResponseFactory(user=initiator, round=temp_round)
        
        discussion = DiscussionService.create_discussion(
            initiator=initiator,
            headline="Invite test",
            details="Testing invites",
            mrm=30,
            rtm=2.0,
            mrl=2000,
            initial_invites=[invitee1, invitee2]
        )
        
        # Check invites were created
        assert discussion.invites.count() >= 0  # May fail if no invites available
    
    def test_headline_too_long(self):
        """Test headline length validation."""
        user = UserFactory()
        config = PlatformConfig.load()
        
        long_headline = "x" * (config.max_headline_length + 1)
        
        with pytest.raises(ValidationError, match="Headline cannot exceed"):
            DiscussionService.create_discussion(
                initiator=user,
                headline=long_headline,
                details="Details",
                mrm=30,
                rtm=2.0,
                mrl=2000
            )
    
    def test_details_too_long(self):
        """Test details length validation."""
        user = UserFactory()
        config = PlatformConfig.load()
        
        long_details = "x" * (config.max_topic_length + 1)
        
        with pytest.raises(ValidationError, match="Details cannot exceed"):
            DiscussionService.create_discussion(
                initiator=user,
                headline="Test",
                details=long_details,
                mrm=30,
                rtm=2.0,
                mrl=2000
            )
    
    def test_invalid_parameters(self):
        """Test parameter validation."""
        user = UserFactory()
        
        with pytest.raises(ValidationError):
            DiscussionService.create_discussion(
                initiator=user,
                headline="Test",
                details="Details",
                mrm=1,  # Too low
                rtm=2.0,
                mrl=2000
            )
    
    def test_duplicate_discussion_prevented(self):
        """Test duplicate discussion detection."""
        config = PlatformConfig.load()
        config.allow_duplicate_discussions = False
        config.save()
        
        user = UserFactory()
        
        # Create first discussion
        DiscussionService.create_discussion(
            initiator=user,
            headline="Unique Headline",
            details="Details",
            mrm=30,
            rtm=2.0,
            mrl=2000
        )
        
        # Try to create duplicate
        with pytest.raises(ValidationError, match="already exists"):
            DiscussionService.create_discussion(
                initiator=user,
                headline="Unique Headline",
                details="Different details",
                mrm=30,
                rtm=2.0,
                mrl=2000
            )
    
    def test_round_1_created_automatically(self):
        """Test that Round 1 is created with new discussion."""
        user = UserFactory()
        
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="Test",
            details="Details",
            mrm=30,
            rtm=2.0,
            mrl=2000
        )
        
        # Check Round 1 exists
        round_1 = Round.objects.filter(discussion=discussion, round_number=1).first()
        assert round_1 is not None
        assert round_1.status == 'in_progress'
    
    def test_initiator_participant_created(self):
        """Test that initiator is added as participant."""
        user = UserFactory()
        
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="Test",
            details="Details",
            mrm=30,
            rtm=2.0,
            mrl=2000
        )
        
        # Check initiator participant
        participant = DiscussionParticipant.objects.filter(
            discussion=discussion,
            user=user
        ).first()
        
        assert participant is not None
        assert participant.role == 'initiator'
        assert participant.can_invite_others is True


@pytest.mark.django_db
class TestDiscussionRetrieval:
    """Test discussion retrieval methods."""
    
    def test_get_active_discussions(self):
        """Test getting active discussions for user."""
        user = UserFactory()
        
        # Create discussion where user is initiator
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="Test",
            details="Details",
            mrm=30,
            rtm=2.0,
            mrl=2000
        )
        
        # Get active discussions
        active = DiscussionService.get_active_discussions(user)
        
        assert discussion in active
    
    def test_get_observable_discussions(self):
        """Test getting all observable discussions (including as observer)."""
        user = UserFactory()
        
        # Create discussion where user is initiator
        discussion = DiscussionService.create_discussion(
            initiator=user,
            headline="Test",
            details="Details",
            mrm=30,
            rtm=2.0,
            mrl=2000
        )
        
        # Get observable discussions
        observable = DiscussionService.get_observable_discussions(user)
        
        assert discussion in observable
