"""
Tests for phone-based authentication system.

Tests verification code generation, validation, registration, and login.
"""

import pytest
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock

from core.auth.registration import PhoneVerificationService
from core.models import User, PlatformConfig, Invite
from core.services.invite_service import InviteService


@pytest.mark.django_db
class TestPhoneVerification:
    """Test phone verification service."""
    
    def test_send_verification_code_success(self):
        """Test successful verification code generation."""
        phone = '+12345678900'
        
        with patch('core.tasks.send_verification_sms.delay') as mock_sms:
            verification_id, success, message = PhoneVerificationService.send_verification_code(phone)
            
            assert success is True
            assert verification_id is not None
            assert 'sent' in message.lower()
            
            # Check code was stored in cache
            code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
            stored_code = cache.get(code_key)
            assert stored_code is not None
            assert len(stored_code) == 6
            assert stored_code.isdigit()
            
            # Check SMS task was called
            mock_sms.assert_called_once()
    
    def test_send_verification_invalid_phone(self):
        """Test verification with invalid phone number."""
        from django.core.exceptions import ValidationError
        
        with pytest.raises(ValidationError):
            PhoneVerificationService.send_verification_code('invalid')
    
    def test_send_verification_duplicate_phone(self, user_factory):
        """Test verification fails for existing phone number."""
        from django.core.exceptions import ValidationError
        
        user = user_factory(phone_number='+12345678900')
        
        with pytest.raises(ValidationError) as exc_info:
            PhoneVerificationService.send_verification_code('+12345678900')
        
        assert 'already registered' in str(exc_info.value).lower()
    
    def test_verify_code_success(self):
        """Test successful code verification."""
        phone = '+12345678900'
        
        # Manually create verification
        import uuid
        verification_id = str(uuid.uuid4())
        code = '123456'
        
        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"
        
        cache.set(code_key, code, timeout=600)
        cache.set(phone_key, phone, timeout=600)
        
        # Verify
        is_valid, message, retrieved_phone = PhoneVerificationService.verify_code(
            verification_id, code
        )
        
        assert is_valid is True
        assert retrieved_phone == phone
        
        # Code should be deleted after use
        assert cache.get(code_key) is None
    
    def test_verify_code_wrong_code(self):
        """Test verification with wrong code."""
        import uuid
        verification_id = str(uuid.uuid4())
        
        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"
        
        cache.set(code_key, '123456', timeout=600)
        cache.set(phone_key, '+12345678900', timeout=600)
        
        is_valid, message, phone = PhoneVerificationService.verify_code(
            verification_id, '999999'
        )
        
        assert is_valid is False
        assert phone is None
    
    def test_verify_code_expired(self):
        """Test verification with expired code."""
        import uuid
        verification_id = str(uuid.uuid4())
        
        is_valid, message, phone = PhoneVerificationService.verify_code(
            verification_id, '123456'
        )
        
        assert is_valid is False
        assert 'expired' in message.lower() or 'invalid' in message.lower()
    
    def test_rate_limiting(self, user_factory):
        """Test rate limiting on verification requests."""
        from django.core.exceptions import ValidationError
        
        phone = '+12025551000'  # Valid US format for testing
        
        # Exhaust rate limit
        rate_key = f"{PhoneVerificationService.RATE_LIMIT_PREFIX}{phone}"
        cache.set(rate_key, PhoneVerificationService.MAX_REQUESTS_PER_WINDOW, timeout=3600)
        
        with pytest.raises(ValidationError) as exc_info:
            with patch('core.tasks.send_verification_sms.delay'):
                PhoneVerificationService.send_verification_code(phone)
        
        error_msg = str(exc_info.value).lower()
        assert 'too many' in error_msg or 'rate' in error_msg


@pytest.mark.django_db
class TestAuthenticationAPI:
    """Test authentication API endpoints."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test data."""
        cache.clear()
        # Create platform config
        PlatformConfig.objects.get_or_create(pk=1)
    
    def test_request_verification_endpoint(self, api_client):
        """Test verification request endpoint."""
        with patch('core.tasks.send_verification_sms.delay'):
            response = api_client.post('/api/auth/register/request-verification/', {
                'phone_number': '+12345678900'
            })
        
        assert response.status_code == 200
        assert 'verification_id' in response.data
        assert 'expires_at' in response.data
    
    def test_registration_with_invite(self, api_client, user_factory, discussion_factory, response_factory):
        """Test complete registration flow with invite code."""
        # Create inviter with enough responses to unlock invites
        inviter = user_factory()
        discussion = discussion_factory()
        
        # Create 3 responses to unlock invites
        for _ in range(3):
            response_factory(user=inviter, discussion=discussion)
        
        inviter.platform_invites_banked = 1
        inviter.save()
        
        invite, invite_code = InviteService.send_platform_invite(inviter)
        
        # Request verification
        import uuid
        verification_id = str(uuid.uuid4())
        code = '123456'
        phone = '+19998887777'
        
        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"
        
        cache.set(code_key, code, timeout=600)
        cache.set(phone_key, phone, timeout=600)
        
        # Complete registration
        response = api_client.post('/api/auth/register/verify/', {
            'verification_id': verification_id,
            'code': code,
            'invite_code': invite_code,
            'username': 'newuser'
        })
        
        assert response.status_code == 201
        assert 'user_id' in response.data
        assert 'tokens' in response.data
        assert 'access' in response.data['tokens']
        assert 'refresh' in response.data['tokens']
        
        # Check user was created
        user = User.objects.get(username='newuser')
        assert user.phone_number == phone
        
        # Check invite was accepted
        invite.refresh_from_db()
        assert invite.status == 'accepted'
        assert invite.invitee == user
    
    def test_registration_without_invite(self, api_client):
        """Test registration without invite code."""
        import uuid
        verification_id = str(uuid.uuid4())
        code = '123456'
        phone = '+19998887777'
        
        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        phone_key = f"{PhoneVerificationService.PHONE_PREFIX}{verification_id}"
        
        cache.set(code_key, code, timeout=600)
        cache.set(phone_key, phone, timeout=600)
        
        response = api_client.post('/api/auth/register/verify/', {
            'verification_id': verification_id,
            'code': code,
            'username': 'newuser2'
        })
        
        assert response.status_code == 201
        
        # Check user got starting invites
        user = User.objects.get(username='newuser2')
        config = PlatformConfig.objects.get(pk=1)
        assert user.platform_invites_banked == config.new_user_platform_invites
        assert user.discussion_invites_banked == config.new_user_discussion_invites
    
    def test_login_flow(self, api_client, user_factory):
        """Test complete login flow."""
        user = user_factory(phone_number='+12345678900')
        
        # Request login
        response = api_client.post('/api/auth/login/', {
            'phone_number': '+12345678900'
        })
        
        assert response.status_code == 200
        assert 'verification_id' in response.data
        
        verification_id = response.data['verification_id']
        
        # Get code from cache
        code_key = f"{PhoneVerificationService.CODE_PREFIX}{verification_id}"
        code = cache.get(code_key)
        
        # Verify login
        response = api_client.post('/api/auth/login/verify/', {
            'verification_id': verification_id,
            'code': code
        })
        
        assert response.status_code == 200
        assert 'tokens' in response.data
        assert response.data['user_id'] == str(user.id)
    
    def test_login_nonexistent_user(self, api_client):
        """Test login with non-existent phone number."""
        response = api_client.post('/api/auth/login/', {
            'phone_number': '+12025559999'  # Valid format but non-existent user
        })
        
        assert response.status_code == 404
    
    def test_jwt_token_refresh(self, api_client, user_factory):
        """Test JWT token refresh."""
        from rest_framework_simplejwt.tokens import RefreshToken
        
        user = user_factory()
        refresh = RefreshToken.for_user(user)
        
        response = api_client.post('/api/auth/token/refresh/', {
            'refresh': str(refresh)
        })
        
        assert response.status_code == 200
        assert 'access' in response.data
