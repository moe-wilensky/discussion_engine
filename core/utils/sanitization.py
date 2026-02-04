"""
Content sanitization utilities for user-generated content.

Provides HTML sanitization to prevent XSS attacks while allowing basic formatting.
"""

import bleach
from typing import List


# Allowed HTML tags for basic formatting
ALLOWED_TAGS: List[str] = [
    'p',      # Paragraphs
    'br',     # Line breaks
    'strong', # Bold text
    'em',     # Italic/emphasis
    'b',      # Bold (alternative)
    'i',      # Italic (alternative)
    'u',      # Underline
    'a',      # Links
    'ul',     # Unordered lists
    'ol',     # Ordered lists
    'li',     # List items
    'blockquote',  # Block quotes
]

# Allowed attributes for specific tags
ALLOWED_ATTRIBUTES: dict = {
    'a': ['href', 'title'],  # Links can have href and title
}

# Allowed protocols for links
ALLOWED_PROTOCOLS: List[str] = ['http', 'https', 'mailto']


def clean_content(content: str) -> str:
    """
    Sanitize user-generated content to prevent XSS attacks.

    Removes dangerous HTML/JavaScript while preserving basic formatting tags.

    Args:
        content: Raw user input that may contain HTML

    Returns:
        Sanitized content safe for display

    Examples:
        >>> clean_content('<p>Hello</p>')
        '<p>Hello</p>'

        >>> clean_content('<script>alert("XSS")</script>')
        '&lt;script&gt;alert("XSS")&lt;/script&gt;'

        >>> clean_content('<p>Hello <strong>World</strong></p>')
        '<p>Hello <strong>World</strong></p>'
    """
    if not content:
        return content

    # Use bleach to sanitize the content
    cleaned = bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=False,  # Don't strip tags, escape them instead
    )

    # Additional cleanup: remove excessive whitespace
    cleaned = ' '.join(cleaned.split())

    return cleaned


def strip_all_html(content: str) -> str:
    """
    Strip all HTML tags from content, leaving only plain text.

    Args:
        content: Content that may contain HTML

    Returns:
        Plain text with all HTML removed

    Examples:
        >>> strip_all_html('<p>Hello <strong>World</strong></p>')
        'Hello World'
    """
    if not content:
        return content

    # Remove all HTML tags
    return bleach.clean(content, tags=[], strip=True)


def sanitize_url(url: str) -> str:
    """
    Sanitize a URL to ensure it uses a safe protocol.

    Args:
        url: URL to sanitize

    Returns:
        Sanitized URL or empty string if unsafe

    Examples:
        >>> sanitize_url('https://example.com')
        'https://example.com'

        >>> sanitize_url('javascript:alert("XSS")')
        ''
    """
    if not url:
        return ''

    # Check if URL starts with allowed protocol
    url_lower = url.lower().strip()
    for protocol in ALLOWED_PROTOCOLS:
        if url_lower.startswith(f'{protocol}:'):
            return url

    # If no protocol specified, assume https
    if not any(url_lower.startswith(f'{p}:') for p in ['http:', 'https:', 'mailto:', 'javascript:', 'data:']):
        return f'https://{url}'

    # Unsafe protocol - return empty string
    return ''
