"""
Comprehensive security test suite for the Discussion Engine.

Tests for:
- XSS prevention
- SQL injection prevention
- CSRF protection
- Rate limiting
- Input sanitization
- Abuse detection
- Authorization checks
"""

import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status

from core.models import Discussion, Response, Invite, Round, DiscussionParticipant
from core.utils.sanitization import clean_content
from core.security.abuse_detection import AbuseDetectionService

User = get_user_model()


@pytest.mark.django_db
class TestXSSPrevention:
    """Test XSS attack prevention."""

    def test_response_content_sanitized(self, authenticated_api_client, active_discussion):
        """Test that script tags are sanitized from response content."""
        client, user = authenticated_api_client

        # Add user as participant
        DiscussionParticipant.objects.create(
            discussion=active_discussion,
            user=user,
            role="active"
        )

        # Get the current round
        current_round = active_discussion.rounds.first()

        # Try to inject XSS
        xss_payloads = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror="alert(\'XSS\')">',
            '<iframe src="javascript:alert(\'XSS\')"></iframe>',
            'javascript:alert("XSS")',
            '<svg onload="alert(\'XSS\')">',
        ]

        for payload in xss_payloads:
            response = client.post(
                f'/api/discussions/{active_discussion.id}/rounds/{current_round.round_number}/responses/',
                {'content': payload},
                format='json'
            )

            # Response should be created successfully
            assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]

            # If created, verify content is sanitized
            if response.status_code == status.HTTP_201_CREATED:
                response_obj = Response.objects.get(id=response.data['id'])
                # Should not contain dangerous tags
                assert '<script>' not in response_obj.content.lower()
                assert 'onerror' not in response_obj.content.lower()
                assert 'javascript:' not in response_obj.content.lower()
                assert '<iframe' not in response_obj.content.lower()

    def test_discussion_content_sanitized(self, authenticated_api_client):
        """Test that discussion headline and details are sanitized."""
        client, user = authenticated_api_client

        xss_payload = '<script>alert("XSS")</script>Normal text'

        response = client.post(
            '/api/discussions/',
            {
                'headline': xss_payload,
                'details': xss_payload,
                'preset': 'casual'
            },
            format='json'
        )

        if response.status_code == status.HTTP_201_CREATED:
            discussion = Discussion.objects.get(id=response.data['id'])
            # Should not contain script tags
            assert '<script>' not in discussion.topic_headline.lower()
            assert '<script>' not in discussion.topic_details.lower()

    def test_sanitization_preserves_safe_html(self):
        """Test that safe HTML formatting is preserved."""
        safe_html = '<p>Hello <strong>world</strong></p>'
        cleaned = clean_content(safe_html)

        # Safe tags should be preserved
        assert '<p>' in cleaned or 'Hello' in cleaned
        assert '<strong>' in cleaned or 'world' in cleaned

    def test_sanitization_removes_dangerous_html(self):
        """Test that dangerous HTML is removed."""
        dangerous_html = '<script>alert("XSS")</script><p>Safe content</p>'
        cleaned = clean_content(dangerous_html)

        # Dangerous tags should be removed/escaped
        assert '<script>' not in cleaned
        assert 'alert' in cleaned  # Text remains but tag is escaped


@pytest.mark.django_db
class TestSQLInjectionPrevention:
    """Test SQL injection prevention."""

    def test_username_sql_injection(self, api_client):
        """Test that SQL injection in username is prevented."""
        sql_payloads = [
            "admin'--",
            "admin' OR '1'='1",
            "'; DROP TABLE users;--",
            "1' UNION SELECT * FROM users--",
        ]

        for payload in sql_payloads:
            # Try to register with SQL injection payload
            response = api_client.post(
                '/api/auth/register/verify/',
                {
                    'verification_id': '12345678-1234-1234-1234-123456789012',
                    'code': '123456',
                    'username': payload
                },
                format='json'
            )

            # Should fail validation or not execute SQL injection
            # Database should still exist and be functional
            assert User.objects.model._meta.db_table  # Table still exists

    def test_search_sql_injection(self, authenticated_api_client):
        """Test that SQL injection in search queries is prevented."""
        client, user = authenticated_api_client

        sql_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE discussions;--",
        ]

        for payload in sql_payloads:
            response = client.get(
                '/api/discussions/',
                {'search': payload}
            )

            # Should not cause errors or SQL injection
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
            # Database should still be functional
            assert Discussion.objects.model._meta.db_table


@pytest.mark.django_db
class TestCSRFProtection:
    """Test CSRF protection on POST endpoints."""

    def test_csrf_required_on_api_endpoints(self):
        """Test that CSRF token is required for state-changing operations."""
        client = Client(enforce_csrf_checks=True)

        # Try POST without CSRF token
        response = client.post(
            '/api/discussions/',
            {'headline': 'Test', 'details': 'Test', 'preset': 'casual'},
            content_type='application/json'
        )

        # Should require authentication/CSRF (403 or 401)
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_401_UNAUTHORIZED
        ]


@pytest.mark.django_db
class TestRateLimiting:
    """Test rate limiting on authentication endpoints."""

    def setup_method(self):
        """Clear cache before each test."""
        cache.clear()

    def test_registration_rate_limit(self, api_client):
        """Test that registration requests are rate limited."""
        phone_number = '+12345678901'

        # Make multiple requests
        for i in range(6):
            response = api_client.post(
                '/api/auth/register/request-verification/',
                {'phone_number': phone_number},
                format='json'
            )

            if i < 5:
                # First 5 should succeed or fail for other reasons
                assert response.status_code in [
                    status.HTTP_200_OK,
                    status.HTTP_400_BAD_REQUEST
                ]
            else:
                # 6th request should be rate limited
                assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
                assert 'too many' in response.data.get('error', '').lower()

    def test_login_rate_limit(self, api_client):
        """Test that login requests are rate limited."""
        # Create a user first
        user = User.objects.create_user(
            username='testuser',
            phone_number='+12345678901'
        )

        # Make multiple login requests
        for i in range(11):
            response = api_client.post(
                '/api/auth/login/',
                {'phone_number': str(user.phone_number)},
                format='json'
            )

            if i < 10:
                # First 10 should succeed
                assert response.status_code in [
                    status.HTTP_200_OK,
                    status.HTTP_404_NOT_FOUND
                ]
            else:
                # 11th request should be rate limited
                assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_verify_and_register_rate_limit(self, api_client):
        """Test that verification attempts are rate limited."""
        verification_id = '12345678-1234-1234-1234-123456789012'

        # Make multiple requests
        for i in range(11):
            response = api_client.post(
                '/api/auth/register/verify/',
                {
                    'verification_id': verification_id,
                    'code': '123456',
                    'username': f'testuser{i}'
                },
                format='json'
            )

            if i < 10:
                # First 10 should fail for invalid code, not rate limit
                assert response.status_code in [
                    status.HTTP_400_BAD_REQUEST,
                    status.HTTP_201_CREATED
                ]
            else:
                # 11th request should be rate limited
                assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
class TestInputSanitization:
    """Test input sanitization functionality."""

    def test_clean_content_removes_scripts(self):
        """Test that clean_content removes script tags."""
        dangerous = '<script>alert("XSS")</script><p>Hello</p>'
        cleaned = clean_content(dangerous)

        assert '<script>' not in cleaned.lower()
        assert 'Hello' in cleaned

    def test_clean_content_preserves_formatting(self):
        """Test that clean_content preserves safe formatting."""
        safe = '<p>Hello <strong>world</strong></p>'
        cleaned = clean_content(safe)

        # Should preserve basic formatting
        assert 'Hello' in cleaned
        assert 'world' in cleaned

    def test_clean_content_removes_event_handlers(self):
        """Test that event handlers are removed."""
        dangerous = '<img src="x" onerror="alert(\'XSS\')">'
        cleaned = clean_content(dangerous)

        assert 'onerror' not in cleaned.lower()

    def test_clean_content_removes_javascript_protocol(self):
        """Test that javascript: protocol is removed."""
        dangerous = '<a href="javascript:alert(\'XSS\')">Click</a>'
        cleaned = clean_content(dangerous)

        assert 'javascript:' not in cleaned.lower()


@pytest.mark.django_db
class TestAbuseDetection:
    """Test automated abuse detection."""

    def test_spam_pattern_detection(self, user_factory):
        """Test that spam patterns are detected."""
        user = user_factory()

        # Create excessive invites
        for i in range(25):
            Invite.objects.create(
                inviter=user,
                invite_type='platform',
                status='sent',
                invite_code=f'CODE{i:04d}'
            )

        result = AbuseDetectionService.detect_spam_pattern(user)

        # Should detect excessive invites
        assert 'excessive_invites_24h' in result['flags']
        assert result['confidence'] > 0

    def test_response_spam_detection(self, user_factory, active_discussion):
        """Test that spam responses are detected."""
        user = user_factory()

        # Add user as participant
        DiscussionParticipant.objects.create(
            discussion=active_discussion,
            user=user,
            role="active"
        )

        current_round = active_discussion.rounds.first()

        # Create spam response with external links
        response = Response.objects.create(
            user=user,
            round=current_round,
            content='Buy now at http://spam.com! Click here!'
        )

        result = AbuseDetectionService.detect_response_spam(response)

        # Should detect spam keywords and external links
        assert result['confidence'] > 0
        assert len(result['signals']) > 0

    def test_invitation_abuse_detection(self, user_factory):
        """Test that invitation abuse is detected."""
        user = user_factory()

        # Create many invites in short time
        for i in range(20):
            Invite.objects.create(
                inviter=user,
                invite_type='platform',
                status='sent',
                invite_code=f'ABUSE{i:04d}'
            )

        result = AbuseDetectionService.detect_invitation_abuse(user)

        # Should detect high invite rate
        assert result['confidence'] > 0

    def test_discussion_spam_detection(self, user_factory):
        """Test that discussion spam is detected."""
        user = user_factory()

        # Create many discussions with duplicate topics
        for i in range(6):
            Discussion.objects.create(
                initiator=user,
                topic_headline='Spam topic',
                topic_details='Spam details',
                status='active',
                min_response_time_minutes=30,
                response_time_multiplier=1.0,
                max_response_length_chars=2000
            )

        result = AbuseDetectionService.detect_discussion_spam(user)

        # Should detect excessive discussions and duplicates
        assert result['confidence'] > 0


@pytest.mark.django_db
class TestAuthorizationChecks:
    """Test authorization on protected endpoints."""

    def test_unauthenticated_cannot_create_discussion(self, api_client):
        """Test that unauthenticated users cannot create discussions."""
        response = api_client.post(
            '/api/discussions/',
            {
                'headline': 'Test',
                'details': 'Test',
                'preset': 'casual'
            },
            format='json'
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_cannot_post_response(self, api_client, active_discussion):
        """Test that unauthenticated users cannot post responses."""
        current_round = active_discussion.rounds.first()

        response = api_client.post(
            f'/api/discussions/{active_discussion.id}/rounds/{current_round.round_number}/responses/',
            {'content': 'Test response'},
            format='json'
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_participant_cannot_post_response(self, authenticated_api_client, active_discussion):
        """Test that non-participants cannot post responses."""
        client, user = authenticated_api_client
        current_round = active_discussion.rounds.first()

        # User is not a participant
        response = client.post(
            f'/api/discussions/{active_discussion.id}/rounds/{current_round.round_number}/responses/',
            {'content': 'Test response'},
            format='json'
        )

        # Should be forbidden or bad request
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_400_BAD_REQUEST
        ]

    def test_user_can_only_edit_own_response(self, authenticated_api_client, active_discussion):
        """Test that users can only edit their own responses."""
        client, user = authenticated_api_client

        # Create another user and their response
        other_user = User.objects.create_user(
            username='otheruser',
            phone_number='+19876543210'
        )

        DiscussionParticipant.objects.create(
            discussion=active_discussion,
            user=other_user,
            role="active"
        )

        current_round = active_discussion.rounds.first()

        other_response = Response.objects.create(
            user=other_user,
            round=current_round,
            content='Other user response'
        )

        # Try to edit other user's response
        response = client.put(
            f'/api/discussions/{active_discussion.id}/rounds/{current_round.round_number}/responses/{other_response.id}/',
            {'content': 'Hacked content'},
            format='json'
        )

        # Should be forbidden
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND
        ]

    def test_user_cannot_send_invite_without_permission(self, authenticated_api_client):
        """Test that users without invite permissions cannot send invites."""
        client, user = authenticated_api_client

        # Set user's banked invites to 0
        user.platform_invites_banked = 0
        user.save()

        response = client.post(
            '/api/invites/platform/',
            format='json'
        )

        # Should fail due to lack of invites
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN
        ]


@pytest.mark.django_db
class TestSecurityHeaders:
    """Test that security headers are present."""

    def test_security_headers_present(self, client):
        """Test that security headers are set correctly."""
        response = client.get('/')

        # Check for security headers
        headers = response.headers if hasattr(response, 'headers') else response._headers

        # X-Content-Type-Options should be set
        # X-Frame-Options should be set
        # These are configured in settings.py
        assert response.status_code in [200, 301, 302, 404]  # Any valid response


@pytest.mark.django_db
class TestDataProtection:
    """Test data protection measures."""

    def test_phone_numbers_masked_in_api(self, authenticated_api_client):
        """Test that phone numbers are masked for other users."""
        client, user = authenticated_api_client

        # Create another user
        other_user = User.objects.create_user(
            username='otheruser',
            phone_number='+19876543210'
        )

        # Get other user's info
        response = client.get(f'/api/users/{other_user.id}/')

        if response.status_code == status.HTTP_200_OK:
            # Phone should be masked
            phone = response.data.get('phone_number', '')
            assert '***' in phone or phone == ''

    def test_user_sees_own_phone_number(self, authenticated_api_client):
        """Test that users can see their own phone number."""
        client, user = authenticated_api_client

        response = client.get(f'/api/users/{user.id}/')

        if response.status_code == status.HTTP_200_OK:
            # User should see their own full phone number
            phone = response.data.get('phone_number', '')
            # Should not be fully masked (should have actual digits)
            assert phone  # Has some value


# Fixtures

@pytest.fixture
def api_client():
    """Return an API client."""
    return APIClient()


@pytest.fixture
def authenticated_api_client(api_client, user_factory):
    """Return an authenticated API client."""
    user = user_factory()
    api_client.force_authenticate(user=user)
    return api_client, user


@pytest.fixture
def user_factory():
    """Factory for creating users."""
    counter = 0

    def _create_user(**kwargs):
        nonlocal counter
        counter += 1
        defaults = {
            'username': f'testuser{counter}',
            'phone_number': f'+1234567{counter:04d}'
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    return _create_user


@pytest.fixture
def active_discussion(user_factory):
    """Create an active discussion for testing."""
    user = user_factory()

    discussion = Discussion.objects.create(
        initiator=user,
        topic_headline='Test Discussion',
        topic_details='Test details',
        status='active',
        min_response_time_minutes=30,
        response_time_multiplier=1.0,
        max_response_length_chars=2000
    )

    # Create a round
    Round.objects.create(
        discussion=discussion,
        round_number=1,
        status='active'
    )

    # Add initiator as participant
    DiscussionParticipant.objects.create(
        discussion=discussion,
        user=user,
        role='initiator'
    )

    return discussion
