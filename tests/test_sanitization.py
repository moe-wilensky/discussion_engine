"""Tests for content sanitization utilities."""

from django.test import TestCase
from core.utils.sanitization import clean_content, strip_all_html, sanitize_url


class TestCleanContent(TestCase):
    """Tests for the clean_content function."""

    def test_empty_input(self):
        assert clean_content("") == ""
        assert clean_content(None) is None

    def test_allowed_tags_preserved(self):
        assert "<p>" in clean_content("<p>Hello</p>")
        assert "<strong>" in clean_content("<strong>Bold</strong>")
        assert "<em>" in clean_content("<em>Italic</em>")
        assert "<a" in clean_content('<a href="https://example.com">Link</a>')
        assert "<ul>" in clean_content("<ul><li>Item</li></ul>")
        assert "<blockquote>" in clean_content("<blockquote>Quote</blockquote>")

    def test_script_tags_escaped(self):
        result = clean_content('<script>alert("XSS")</script>')
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_event_handlers_removed(self):
        result = clean_content('<p onclick="alert(1)">Click</p>')
        assert "onclick" not in result

    def test_excessive_whitespace_normalized(self):
        result = clean_content("Hello    World")
        assert result == "Hello World"

    def test_link_attributes_filtered(self):
        result = clean_content('<a href="https://example.com" title="Link" class="bad">Link</a>')
        assert 'href="https://example.com"' in result
        assert 'title="Link"' in result
        assert "class=" not in result


class TestStripAllHtml(TestCase):
    """Tests for the strip_all_html function."""

    def test_empty_input(self):
        assert strip_all_html("") == ""
        assert strip_all_html(None) is None

    def test_strips_all_tags(self):
        result = strip_all_html("<p>Hello <strong>World</strong></p>")
        assert result == "Hello World"

    def test_strips_links(self):
        result = strip_all_html('<a href="https://example.com">Link Text</a>')
        assert result == "Link Text"

    def test_plain_text_unchanged(self):
        assert strip_all_html("Just plain text") == "Just plain text"


class TestSanitizeUrl(TestCase):
    """Tests for the sanitize_url function."""

    def test_empty_input(self):
        assert sanitize_url("") == ""
        assert sanitize_url(None) == ""

    def test_https_url_preserved(self):
        assert sanitize_url("https://example.com") == "https://example.com"

    def test_http_url_preserved(self):
        assert sanitize_url("http://example.com") == "http://example.com"

    def test_mailto_preserved(self):
        assert sanitize_url("mailto:test@example.com") == "mailto:test@example.com"

    def test_javascript_blocked(self):
        assert sanitize_url("javascript:alert(1)") == ""

    def test_data_uri_blocked(self):
        assert sanitize_url("data:text/html,<script>alert(1)</script>") == ""

    def test_no_protocol_gets_https(self):
        assert sanitize_url("example.com") == "https://example.com"

    def test_whitespace_handled(self):
        # The function checks url_lower (stripped) but returns original url
        result = sanitize_url("  https://example.com  ")
        assert "https://example.com" in result
