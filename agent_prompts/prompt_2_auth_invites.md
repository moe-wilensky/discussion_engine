# Prompt 2: User Authentication & Invite System

## Objective
Implement complete user authentication (phone-based), invite system (platform and discussion invites), and user onboarding flow with comprehensive API endpoints and automated testing.

## Prerequisites
✅ Prompt 1 completed: All database models exist and tests pass

## Context
Build on the foundation from Prompt 1. This prompt adds the authentication layer and invite mechanics that control platform access and discussion participation.

## Requirements

### 1. Package Installation
Install additional packages within `.venv`:
- django-phonenumber-field
- phonenumbers
- djangorestframework-simplejwt (JWT authentication)
- drf-spectacular (API documentation)
- celery (background tasks)
- redis (Celery broker)
- twilio (SMS verification - use test credentials)

### 2. Phone-Based Authentication System

#### User Registration Flow
Create in `core/auth/registration.py`:

```python
class PhoneVerificationService:
    """
    Handle phone number verification via SMS
    - Send verification code (6 digits)
    - Verify code (time-limited, 10 minutes)
    - Detect duplicate accounts (phone number uniqueness)
    - Behavioral spam detection (rate limiting)
    """
    
    def send_verification_code(phone: str) -> str:
        # Generate 6-digit code
        # Store in cache with 10-minute expiry
        # Send via Twilio (mock in tests)
        # Return verification_id
        pass
    
    def verify_code(verification_id: str, code: str) -> bool:
        # Check code validity and expiry
        # Mark phone as verified
        pass
```

#### Registration Endpoints
Create in `core/api/auth.py`:

**POST /api/auth/register/request-verification/**
```json
Request: {"phone_number": "+1234567890"}
Response: {"verification_id": "uuid", "expires_at": "timestamp"}
```

**POST /api/auth/register/verify/**
```json
Request: {
  "verification_id": "uuid",
  "code": "123456",
  "inviter_code": "optional-if-phone-invite"
}
Response: {
  "user_id": "uuid",
  "tokens": {"access": "jwt", "refresh": "jwt"},
  "invite_allocation": {
    "platform_invites": 0,
    "discussion_invites": 0,
    "responses_needed_to_unlock": 5
  }
}
```

**POST /api/auth/login/**
```json
Request: {"phone_number": "+1234567890"}
Response: {"verification_id": "uuid"}
# Then verify with code as above
```

**POST /api/auth/token/refresh/**
```json
Request: {"refresh": "jwt"}
Response: {"access": "jwt"}
```

### 3. Invite System Implementation

#### Invite Service
Create in `core/services/invite_service.py`:

```python
class InviteService:
    """
    Core invite business logic
    """
    
    @staticmethod
    def can_send_invite(user: User, invite_type: str) -> tuple[bool, str]:
        """Check if user has invites available"""
        # Check responses_to_unlock_invites threshold
        # Check banked invites > 0
        # Return (can_send, reason_if_not)
    
    @staticmethod
    def send_platform_invite(inviter: User) -> Invite:
        """Generate unique invite code for platform"""
        # Create Invite record
        # Consume inviter's banked invite (if config = 'sent')
        # Generate unique 8-character code
        # Return invite
    
    @staticmethod
    def send_discussion_invite(
        inviter: User, 
        discussion: Discussion, 
        invitee: User
    ) -> Invite:
        """Invite user to specific discussion"""
        # Validate inviter is active participant
        # Validate discussion not at cap
        # Create Invite record
        # Consume invite based on config
        # Send notification to invitee
    
    @staticmethod
    def accept_invite(invite: Invite, user: User) -> None:
        """Accept an invite"""
        # Update invite status
        # Consume invite if config = 'accepted'
        # Add user to discussion participants (if discussion invite)
        # Grant new user starting invites (if platform invite)
    
    @staticmethod
    def track_first_participation(user: User, discussion: Discussion) -> None:
        """Track when invited user first participates"""
        # Find relevant discussion invite
        # Update first_participation_at
        # Consume invite if not already consumed
    
    @staticmethod
    def earn_invite_from_response(user: User) -> None:
        """Called after each response submission"""
        # Get config: responses_per_platform_invite, responses_per_discussion_invite
        # Count user's total responses
        # Calculate earned invites
        # Update user.X_invites_acquired
        # Update user.X_invites_banked
```

#### Invite API Endpoints
Create in `core/api/invites.py`:

**GET /api/invites/me/**
```json
Response: {
  "platform_invites": {
    "acquired": 10,
    "used": 3,
    "banked": 7,
    "can_send": true,
    "responses_needed_to_unlock": 0
  },
  "discussion_invites": {
    "acquired": 25,
    "used": 15,
    "banked": 10,
    "can_send": true
  },
  "total_responses": 30
}
```

**POST /api/invites/platform/send/**
```json
Request: {}
Response: {
  "invite_code": "ABC123XY",
  "invite_url": "https://platform.com/join/ABC123XY"
}
```

**POST /api/invites/platform/accept/**
```json
Request: {"invite_code": "ABC123XY"}
Response: {"message": "Invite accepted", "inviter": "username"}
```

**POST /api/invites/discussion/send/**
```json
Request: {
  "discussion_id": "uuid",
  "invitee_user_id": "uuid"
}
Response: {
  "invite_id": "uuid",
  "invitee": "username",
  "discussion": "topic_headline"
}
```

**GET /api/invites/received/**
```json
Response: {
  "pending": [
    {
      "id": "uuid",
      "type": "discussion",
      "discussion": {"id": "uuid", "headline": "..."},
      "inviter": "username",
      "sent_at": "timestamp"
    }
  ],
  "accepted": [...],
  "declined": [...]
}
```

**POST /api/invites/{invite_id}/accept/**
**POST /api/invites/{invite_id}/decline/**

**GET /api/users/{user_id}/invite-metrics/**
```json
Response: {
  "platform_invites": {"acquired": 5, "used": 2, "banked": 3},
  "discussion_invites": {"acquired": 10, "used": 7, "banked": 3},
  "is_penalized": false  // true if acquired > (used + banked)
}
```

### 4. User Onboarding Experience

#### Onboarding Tutorial
Create in `core/services/onboarding.py`:

```python
class OnboardingService:
    """
    First-time user experience
    """
    
    @staticmethod
    def get_tutorial_steps() -> List[dict]:
        """Return onboarding tutorial content"""
        return [
            {
                "step": 1,
                "title": "Welcome to Discussion Engine",
                "content": "...",
                "media": "intro_video.mp4"
            },
            # ... 5-7 tutorial steps
        ]
    
    @staticmethod
    def get_suggested_discussions(user: User) -> QuerySet:
        """Curate discussions for new users"""
        # Active discussions welcoming newcomers
        # Recently archived high-quality discussions
        # Sorted by activity
    
    @staticmethod
    def mark_tutorial_complete(user: User) -> None:
        """Track tutorial completion"""
        pass
```

**GET /api/onboarding/tutorial/**
**POST /api/onboarding/tutorial/complete/**
**GET /api/onboarding/suggested-discussions/**

### 5. Join Request System

#### Join Request Service
Create in `core/services/join_request.py`:

```python
class JoinRequestService:
    """
    Handle observer requests to join discussions
    """
    
    @staticmethod
    def create_request(
        discussion: Discussion,
        requester: User,
        message: str
    ) -> JoinRequest:
        """Observer requests to join discussion"""
        # Validate requester is observer or never joined
        # Validate discussion not at cap
        # Create JoinRequest
        # Notify discussion initiator/approver
    
    @staticmethod
    def approve_request(request: JoinRequest, approver: User) -> None:
        """Approve join request"""
        # Validate approver has authority (initiator or delegated)
        # Add requester to DiscussionParticipant (role: active)
        # Update request status
        # Notify requester
    
    @staticmethod
    def decline_request(
        request: JoinRequest, 
        approver: User,
        message: str
    ) -> None:
        """Decline join request"""
        # Update request status
        # Notify requester with optional message
```

**POST /api/discussions/{discussion_id}/join-request/**
```json
Request: {"message": "I'd love to participate because..."}
Response: {"request_id": "uuid", "status": "pending"}
```

**GET /api/discussions/{discussion_id}/join-requests/**
```json
Response: {
  "pending": [
    {
      "id": "uuid",
      "requester": {"id": "uuid", "username": "..."},
      "message": "...",
      "created_at": "...",
      "invite_metrics": {...}
    }
  ]
}
```

**POST /api/join-requests/{request_id}/approve/**
**POST /api/join-requests/{request_id}/decline/**
```json
Request: {"response_message": "Optional message to requester"}
```

### 6. Automated Testing

Create comprehensive tests in `tests/`:

#### `test_auth.py`
- ✅ Phone verification code generation and validation
- ✅ Code expiry (10 minutes)
- ✅ Duplicate phone number rejection
- ✅ Registration with valid invite code
- ✅ Registration without invite (should fail)
- ✅ JWT token generation and refresh
- ✅ Rate limiting on verification requests

#### `test_invites.py`
- ✅ Platform invite creation and consumption
- ✅ Discussion invite creation and consumption
- ✅ Invite consumption triggers ('sent' vs 'accepted')
- ✅ First participation tracking
- ✅ Earning invites from responses (calculation)
- ✅ Invite formula: acquired = used + banked
- ✅ Responses_to_unlock_invites threshold
- ✅ Can't send invite without sufficient banked
- ✅ Invite acceptance flow
- ✅ Invite decline (doesn't consume inviter's invite)
- ✅ Invite metrics public visibility

#### `test_join_requests.py`
- ✅ Create join request as observer
- ✅ Approve request (adds to participants)
- ✅ Decline request
- ✅ Only initiator/delegated approver can approve
- ✅ Can't join if discussion at cap
- ✅ Notifications sent correctly

#### `test_onboarding.py`
- ✅ Tutorial content retrieval
- ✅ Tutorial completion tracking
- ✅ Suggested discussions algorithm

#### API Integration Tests (`test_api_integration.py`)
- ✅ Complete registration flow (end-to-end)
- ✅ Complete invite acceptance flow
- ✅ Complete join request flow
- ✅ Authentication required for protected endpoints
- ✅ Permission checks (can't invite if not participant)

#### Test Coverage Target: ≥ 90% for all services and API endpoints

### 7. API Documentation

Configure drf-spectacular:
- Auto-generate OpenAPI schema
- Add endpoint descriptions and examples
- Document all request/response schemas
- Available at: `/api/schema/` and `/api/docs/`

### 8. Background Tasks (Celery)

Create in `core/tasks.py`:

```python
@shared_task
def send_verification_sms(phone_number: str, code: str):
    """Send SMS via Twilio (async)"""
    pass

@shared_task
def send_invite_notification(invite_id: str):
    """Notify user of new invite"""
    pass

@shared_task
def cleanup_expired_invites():
    """Periodic task: expire old invites"""
    pass
```

Configure Celery beat for periodic tasks.

### 9. Security & Anti-Abuse

Implement in `core/security/abuse_detection.py`:

```python
class AbuseDetectionService:
    """
    Detect and prevent abusive behavior
    """
    
    @staticmethod
    def check_rate_limit(identifier: str, action: str) -> bool:
        """Rate limiting (Redis-based)"""
        # verification requests: 3 per hour per phone
        # invite sends: 10 per hour per user
        pass
    
    @staticmethod
    def detect_spam_pattern(user: User) -> dict:
        """Behavioral analysis for spam"""
        # Too many rapid invites sent
        # Too many declined invites
        # No actual participation
        # Return: {"is_spam": bool, "confidence": float, "flags": []}
    
    @staticmethod
    def flag_for_review(user: User, reason: str) -> None:
        """Flag user for admin review"""
        pass
```

### 10. Project Structure Update

```
discussion_platform/
├── core/
│   ├── models.py (from Prompt 1)
│   ├── admin.py
│   ├── auth/
│   │   ├── registration.py
│   │   └── backends.py
│   ├── services/
│   │   ├── invite_service.py
│   │   ├── join_request.py
│   │   └── onboarding.py
│   ├── security/
│   │   └── abuse_detection.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── invites.py
│   │   ├── users.py
│   │   └── serializers.py
│   ├── tasks.py (Celery)
│   └── urls.py
├── tests/
│   ├── test_auth.py
│   ├── test_invites.py
│   ├── test_join_requests.py
│   ├── test_onboarding.py
│   ├── test_api_integration.py
│   └── test_security.py
└── celery.py
```

### 11. Success Criteria

✅ All authentication endpoints working (registration, login, token refresh)
✅ Phone verification SMS sent (mocked in tests)
✅ Invite system fully functional (send, accept, decline)
✅ Invite consumption triggers configurable and working
✅ Invite earning from responses working
✅ Join request flow complete
✅ Onboarding tutorial accessible
✅ All tests passing (≥90% coverage)
✅ API documentation generated and accessible
✅ Rate limiting working
✅ JWT authentication working
✅ Celery tasks registered and executable
✅ No security vulnerabilities (run `bandit`)

## Coding Standards

- Use Django REST Framework serializers for validation
- Follow RESTful API design principles
- Add comprehensive docstrings to all services
- Use type hints everywhere
- Handle all edge cases with appropriate error messages
- Log all security-relevant events
- Use Django permissions framework
- Validate all user inputs
- Use transactions for multi-step operations
- Cache frequently accessed data (Redis)

## Autonomous Operation

- Install all packages automatically
- Create migrations for any model changes
- Run all tests automatically
- Generate API documentation automatically
- Start Celery worker for test execution
- Mock external services (Twilio) in tests
- NO user interaction required

## Output

Provide:
1. API endpoints created (count, URLs)
2. Test results (passed, coverage %)
3. API documentation URL
4. Any security warnings
5. Performance metrics (if any slow queries)
6. Next steps for Prompt 3

## Critical Notes

- Mock Twilio in tests (use environment variable for real credentials)
- All SMS sending must be async (Celery tasks)
- Use Redis for rate limiting and code storage
- Ensure invite formula validation in all operations
- Test invite consumption triggers thoroughly (sent vs accepted)
- Document any assumptions about phone number formats
- Consider international phone numbers
