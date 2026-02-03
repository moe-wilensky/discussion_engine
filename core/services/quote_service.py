"""
Quote service for referencing other responses.

Handles creation and formatting of quotes from responses.
"""

import re
from typing import Dict, List, Optional
from django.core.exceptions import ValidationError

from core.models import Response


class QuoteService:
    """Quote and reference other responses."""
    
    @staticmethod
    def create_quote(
        source_response: Response,
        quoted_text: str,
        start_index: int = 0,
        end_index: Optional[int] = None
    ) -> Dict:
        """
        Create a quote reference from a response.
        
        Args:
            source_response: Response being quoted
            quoted_text: The text being quoted
            start_index: Start position in original content
            end_index: End position in original content
            
        Returns:
            Dictionary with quote metadata:
            {
                "response_id": uuid,
                "author": username,
                "response_number": int,
                "quoted_text": str,
                "timestamp": datetime
            }
            
        Raises:
            ValidationError: If quote text not found in response
        """
        # Validate that quoted text exists in response
        if quoted_text not in source_response.content:
            raise ValidationError("Quoted text not found in source response")
        
        # Get response number in round
        from core.services.response_service import ResponseService
        response_number = ResponseService.get_response_number(source_response)
        
        quote_data = {
            "response_id": str(source_response.id),
            "author": source_response.user.username,
            "response_number": response_number,
            "quoted_text": quoted_text,
            "timestamp": source_response.created_at.isoformat(),
            "round_number": source_response.round.round_number
        }
        
        return quote_data
    
    @staticmethod
    def format_quote_for_display(quote: Dict) -> str:
        """
        Format a quote for display in markdown.
        
        Args:
            quote: Quote dictionary from create_quote
            
        Returns:
            Markdown-formatted quote string
            
        Example:
            > [Username] (Response #3):
            > "The original quoted text appears here..."
        """
        author = quote.get('author', 'Unknown')
        response_num = quote.get('response_number', '?')
        quoted_text = quote.get('quoted_text', '')
        
        # Format as markdown blockquote
        formatted = f"> [{author}] (Response #{response_num}):\n"
        formatted += f'> "{quoted_text}"'
        
        return formatted
    
    @staticmethod
    def extract_quotes_from_content(content: str) -> List[Dict]:
        """
        Parse content to extract embedded quotes.
        
        Looks for markdown-style quotes with metadata:
        > [Username] (Response #3):
        > "quoted text"
        
        Args:
            content: Content to parse
            
        Returns:
            List of quote dictionaries
        """
        quotes = []
        
        # Pattern to match quote format
        # > [Username] (Response #N):
        # > "quoted text"
        pattern = r'> \[([^\]]+)\] \(Response #(\d+)\):\n> "([^"]+)"'
        
        matches = re.finditer(pattern, content, re.MULTILINE)
        
        for match in matches:
            quote = {
                "author": match.group(1),
                "response_number": int(match.group(2)),
                "quoted_text": match.group(3)
            }
            quotes.append(quote)
        
        return quotes
    
    @staticmethod
    def create_quote_markdown(
        source_response: Response,
        quoted_text: str
    ) -> str:
        """
        Create and format a quote in one step.
        
        Convenience method that combines create_quote and format_quote_for_display.
        
        Args:
            source_response: Response being quoted
            quoted_text: The text to quote
            
        Returns:
            Markdown-formatted quote string
        """
        quote_data = QuoteService.create_quote(source_response, quoted_text)
        return QuoteService.format_quote_for_display(quote_data)
    
    @staticmethod
    def validate_quote_syntax(content: str) -> bool:
        """
        Validate that quote syntax in content is properly formatted.
        
        Args:
            content: Content to validate
            
        Returns:
            True if all quotes are properly formatted
        """
        # Check for quote-like patterns
        quote_starts = re.findall(r'> \[([^\]]+)\]', content)
        
        if not quote_starts:
            return True  # No quotes, syntax is fine
        
        # Ensure each quote has proper format
        pattern = r'> \[([^\]]+)\] \(Response #(\d+)\):\n> "([^"]+)"'
        matches = re.findall(pattern, content, re.MULTILINE)
        
        # Should have same number of matches as quote starts
        return len(matches) == len(quote_starts)
