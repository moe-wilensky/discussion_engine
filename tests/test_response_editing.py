"""
Tests for response editing with budget tracking.
"""

import pytest
from django.core.exceptions import ValidationError

from core.models import PlatformConfig
from core.services.response_service import ResponseService
from tests.factories import UserFactory, DiscussionFactory, RoundFactory, ResponseFactory


@pytest.mark.django_db
class TestResponseEditing:
    """Test response editing functionality."""
    
    def test_edit_within_budget(self):
        """Test editing response within 20% budget."""
        config = PlatformConfig.load()
        config.response_edit_percentage = 50  # 50% for easier testing
        config.response_edit_limit = 2
        config.save()
        
        user = UserFactory()
        discussion = DiscussionFactory()
        round_obj = RoundFactory(discussion=discussion)
        
        # Create response with 100 characters
        content = "a" * 100
        response = ResponseFactory(round=round_obj, user=user, content=content)
        
        # Edit changing  10 characters (well within 50 limit)
        new_content = "b" * 10 + "a" * 90
        
        updated = ResponseService.edit_response(user, response, new_content, config)
        
        assert updated.edit_count == 1
        assert updated.content == new_content
    
    def test_edit_exceeds_budget(self):
        """Test that editing beyond budget fails."""
        config = PlatformConfig.load()
        config.response_edit_percentage = 10  # Only 10% allowed
        config.save()
        
        user = UserFactory()
        response = ResponseFactory(user=user, content="a" * 100)
        
        # Try to change more than 10 characters (> 10% limit)
        new_content = "b" * 100  # Complete replacement
        
        with pytest.raises(ValidationError, match="budget"):
            ResponseService.edit_response(user, response, new_content, config)
    
    def test_edit_count_limit(self):
        """Test edit count limit (2 edits max)."""
        config = PlatformConfig.load()
        config.response_edit_limit = 2
        config.response_edit_percentage = 100  # No budget limit to test count limit only
        config.save()
        
        user = UserFactory()
        response = ResponseFactory(user=user, content="Original content here")
        
        # First edit
        response.content = "First edit"
        response.save()
        response.edit_count = 0  # Reset for test
        response.characters_changed_total = 0
        response.save()
        
        ResponseService.edit_response(user, response, "First edit version 1", config)
        response.refresh_from_db()
        assert response.edit_count == 1
        
        # Second edit
        ResponseService.edit_response(user, response, "Second edit version 2", config)
        response.refresh_from_db()
        assert response.edit_count == 2
        
        # Third edit should fail due to count limit
        with pytest.raises(ValidationError, match="Maximum 2 edits"):
            ResponseService.edit_response(user, response, "Third attempt", config)
    
    def test_calculate_characters_changed(self):
        """Test character change calculation."""
        old = "Hello world"
        new = "Hello there world"
        
        chars = ResponseService.calculate_characters_changed(old, new)
        
        # "there " was inserted (6 chars)
        assert chars == 6
    
    def test_cannot_edit_locked_response(self):
        """Test that locked responses cannot be edited."""
        config = PlatformConfig.load()
        user = UserFactory()
        response = ResponseFactory(user=user, is_locked=True)
        
        with pytest.raises(ValidationError, match="locked"):
            ResponseService.edit_response(user, response, "New content", config)
    
    def test_cannot_edit_others_response(self):
        """Test that users can only edit their own responses."""
        config = PlatformConfig.load()
        owner = UserFactory()
        other = UserFactory()
        response = ResponseFactory(user=owner)
        
        with pytest.raises(ValidationError, match="own responses"):
            ResponseService.edit_response(other, response, "Hacked", config)
