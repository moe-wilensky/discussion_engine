"""
Comprehensive tests for quote_service.py
Target: 95%+ coverage

Tests quote creation, validation, extraction, formatting, and retrieval.
"""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.services.quote_service import QuoteService
from core.models import Response, Round, Discussion, User, DiscussionParticipant
from tests.factories import UserFactory, DiscussionFactory, RoundFactory


@pytest.mark.django_db
class TestQuoteCreation:
    """Test quote reference creation"""

    def test_create_quote_basic(self):
        """Test basic quote creation with valid parameters"""
        # Create test data
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="This is a test response with some content to quote.",
            character_count=54
        )
        
        # Create quote
        quoted_text = "test response with some content"
        quote_data = QuoteService.create_quote(response, quoted_text)
        
        # Verify quote data
        assert quote_data["response_id"] == str(response.id)
        assert quote_data["author"] == user.username
        assert quote_data["quoted_text"] == quoted_text
        assert quote_data["round_number"] == 1
        assert "timestamp" in quote_data
        assert "response_number" in quote_data
    
    def test_create_quote_with_indices(self):
        """Test quote creation with start and end indices"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="The quick brown fox jumps over the lazy dog.",
            character_count=45
        )
        
        # Create quote with indices
        quoted_text = "brown fox"
        quote_data = QuoteService.create_quote(
            response, 
            quoted_text, 
            start_index=10, 
            end_index=19
        )
        
        assert quote_data["quoted_text"] == quoted_text
        assert quote_data["author"] == user.username
    
    def test_create_quote_invalid_text(self):
        """Test quote creation with text not in response"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="This is the actual content.",
            character_count=27
        )
        
        # Try to quote text that doesn't exist
        with pytest.raises(ValidationError, match="Quoted text not found"):
            QuoteService.create_quote(response, "This text does not exist")
    
    def test_create_quote_empty_text(self):
        """Test quote creation with empty text - empty string is contained in any string"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="Some content here.",
            character_count=18
        )
        
        # Empty string is technically in any string, so it succeeds
        quote_data = QuoteService.create_quote(response, "")
        assert quote_data["quoted_text"] == ""


@pytest.mark.django_db
class TestQuoteFormatting:
    """Test quote display formatting"""
    
    def test_format_quote_for_display(self):
        """Test basic quote formatting"""
        quote = {
            "author": "testuser",
            "response_number": 5,
            "quoted_text": "This is a test quote"
        }
        
        formatted = QuoteService.format_quote_for_display(quote)
        
        assert "> [testuser] (Response #5):" in formatted
        assert '> "This is a test quote"' in formatted
    
    def test_format_quote_missing_fields(self):
        """Test quote formatting with missing fields"""
        quote = {
            "quoted_text": "Test quote"
        }
        
        formatted = QuoteService.format_quote_for_display(quote)
        
        assert "> [Unknown] (Response #?):" in formatted
        assert '> "Test quote"' in formatted
    
    def test_format_quote_with_special_characters(self):
        """Test quote formatting with special characters"""
        quote = {
            "author": "user_123",
            "response_number": 10,
            "quoted_text": "Quote with 'single' and \"double\" quotes!"
        }
        
        formatted = QuoteService.format_quote_for_display(quote)
        
        assert "> [user_123] (Response #10):" in formatted
        assert "Quote with 'single' and \"double\" quotes!" in formatted


@pytest.mark.django_db
class TestQuoteExtraction:
    """Test extracting quotes from content"""
    
    def test_extract_single_quote(self):
        """Test extracting a single quote from content"""
        content = """Here is some text.

> [alice] (Response #3):
> "This is a quoted response"

And some more text."""
        
        quotes = QuoteService.extract_quotes_from_content(content)
        
        assert len(quotes) == 1
        assert quotes[0]["author"] == "alice"
        assert quotes[0]["response_number"] == 3
        assert quotes[0]["quoted_text"] == "This is a quoted response"
    
    def test_extract_multiple_quotes(self):
        """Test extracting multiple quotes from content"""
        content = """First paragraph.

> [alice] (Response #1):
> "First quote"

Middle paragraph.

> [bob] (Response #5):
> "Second quote"

End paragraph."""
        
        quotes = QuoteService.extract_quotes_from_content(content)
        
        assert len(quotes) == 2
        assert quotes[0]["author"] == "alice"
        assert quotes[0]["response_number"] == 1
        assert quotes[1]["author"] == "bob"
        assert quotes[1]["response_number"] == 5
    
    def test_extract_no_quotes(self):
        """Test extracting from content with no quotes"""
        content = "This is just regular text without any quotes."
        
        quotes = QuoteService.extract_quotes_from_content(content)
        
        assert len(quotes) == 0
    
    def test_extract_malformed_quotes(self):
        """Test that malformed quotes are not extracted"""
        content = """
> [user] Response #3:
> "Missing parentheses"

> user (Response #4):
> "Missing brackets"

> [user] (Response #five):
> "Non-numeric response number"
"""
        
        quotes = QuoteService.extract_quotes_from_content(content)
        
        assert len(quotes) == 0


@pytest.mark.django_db
class TestQuoteMarkdown:
    """Test quote markdown generation"""
    
    def test_create_quote_markdown(self):
        """Test creating formatted quote markdown in one step"""
        user = UserFactory.create(username="quoter")
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="Original response content to be quoted.",
            character_count=40
        )
        
        markdown = QuoteService.create_quote_markdown(
            response, 
            "response content to be"
        )
        
        assert "> [quoter]" in markdown
        assert "> \"response content to be\"" in markdown
        assert "Response #" in markdown
    
    def test_create_quote_markdown_invalid_text(self):
        """Test create_quote_markdown with invalid text"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="Actual content.",
            character_count=15
        )
        
        with pytest.raises(ValidationError):
            QuoteService.create_quote_markdown(response, "Invalid text")


@pytest.mark.django_db
class TestQuoteSyntaxValidation:
    """Test quote syntax validation"""
    
    def test_validate_quote_syntax_valid(self):
        """Test validation of properly formatted quotes"""
        content = """
> [user1] (Response #3):
> "Valid quote"

> [user2] (Response #7):
> "Another valid quote"
"""
        
        assert QuoteService.validate_quote_syntax(content) is True
    
    def test_validate_quote_syntax_no_quotes(self):
        """Test validation of content without quotes"""
        content = "Just regular text without any quotes."
        
        assert QuoteService.validate_quote_syntax(content) is True
    
    def test_validate_quote_syntax_malformed(self):
        """Test validation of malformed quotes"""
        content = """
> [user1] (Response #3):
Missing quote marks here

> [user2] Response #4:
> "Wrong format"
"""
        
        assert QuoteService.validate_quote_syntax(content) is False
    
    def test_validate_quote_syntax_partial(self):
        """Test validation of partially formatted quotes"""
        content = """
> [user1] 
> "Incomplete quote"
"""
        
        assert QuoteService.validate_quote_syntax(content) is False


@pytest.mark.django_db
class TestQuoteEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_quote_with_unicode(self):
        """Test quoting content with unicode characters"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="Unicode text: émojis 😀, Chinese 中文, Arabic العربية",
            character_count=55
        )
        
        quote_data = QuoteService.create_quote(response, "émojis 😀")
        
        assert quote_data["quoted_text"] == "émojis 😀"
    
    def test_quote_very_long_text(self):
        """Test quoting very long text"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        long_content = "A" * 5000
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content=long_content,
            character_count=5000
        )
        
        quote_data = QuoteService.create_quote(response, "A" * 100)
        
        assert len(quote_data["quoted_text"]) == 100
    
    def test_quote_with_newlines(self):
        """Test quoting text with newlines"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="Line one\nLine two\nLine three",
            character_count=30
        )
        
        quote_data = QuoteService.create_quote(response, "Line one\nLine two")
        
        assert "\n" in quote_data["quoted_text"]
    
    def test_extract_quotes_with_nested_brackets(self):
        """Test extracting quotes with nested brackets"""
        content = """
> [user[admin]] (Response #1):
> "This won't match due to nested brackets"

> [normal_user] (Response #2):
> "This will match"
"""
        
        quotes = QuoteService.extract_quotes_from_content(content)
        
        # Should only match the properly formatted one
        assert len(quotes) == 1
        assert quotes[0]["author"] == "normal_user"
    
    def test_format_quote_empty_quoted_text(self):
        """Test formatting quote with empty quoted text"""
        quote = {
            "author": "user",
            "response_number": 1,
            "quoted_text": ""
        }
        
        formatted = QuoteService.format_quote_for_display(quote)
        
        assert "> [user] (Response #1):" in formatted
        assert '> ""' in formatted


@pytest.mark.django_db
class TestQuoteIntegration:
    """Test quote service integration with responses"""
    
    def test_quote_across_rounds(self):
        """Test quoting responses from different rounds"""
        user1 = UserFactory.create(username="user1")
        user2 = UserFactory.create(username="user2")
        discussion = DiscussionFactory.create(initiator=user1)
        
        # Add participant (user1 already has a participant as initiator from factory)
        DiscussionParticipant.objects.create(
            discussion=discussion,
            user=user2,
            role="active"
        )
        
        # Create responses in different rounds
        round1 = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="completed"
        )
        
        response1 = Response.objects.create(
            round=round1,
            user=user1,
            content="First round response",
            character_count=20
        )
        
        round2 = Round.objects.create(
            discussion=discussion,
            round_number=2,
            status="in_progress"
        )
        
        # Quote from round 1
        quote_data = QuoteService.create_quote(response1, "First round")
        
        assert quote_data["round_number"] == 1
        assert quote_data["author"] == "user1"
    
    def test_quote_multiple_from_same_response(self):
        """Test creating multiple quotes from the same response"""
        user = UserFactory.create()
        discussion = DiscussionFactory.create(initiator=user)
        round_obj = Round.objects.create(
            discussion=discussion,
            round_number=1,
            status="in_progress"
        )
        
        response = Response.objects.create(
            round=round_obj,
            user=user,
            content="The quick brown fox jumps over the lazy dog.",
            character_count=45
        )
        
        quote1 = QuoteService.create_quote(response, "quick brown fox")
        quote2 = QuoteService.create_quote(response, "lazy dog")
        
        assert quote1["response_id"] == quote2["response_id"]
        assert quote1["quoted_text"] != quote2["quoted_text"]
        assert quote1["author"] == quote2["author"]
