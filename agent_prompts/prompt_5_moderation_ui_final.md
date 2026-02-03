# Prompt 5: Moderation, Notifications, Admin Tools & Frontend Polish

## Objective
Implement mutual removal system, notification system (critical and optional), admin dashboard, anti-abuse measures, basic frontend UI, and comprehensive integration testing to complete the fully functional Discussion Engine platform.

## Prerequisites
✅ Prompt 1 completed: Database models exist
✅ Prompt 2 completed: Authentication and invites working
✅ Prompt 3 completed: Discussion creation and Round 1 working
✅ Prompt 4 completed: Multi-round voting and observer reintegration working

## Context
This is the final prompt. Complete the platform with moderation features, notification system, admin tools, and a functional frontend interface. Include comprehensive integration tests to ensure the entire system works end-to-end.

## Requirements

### 1. Mutual Removal System (Kamikaze Lite)

#### Mutual Removal Service
Create in `core/services/mutual_removal_service.py`:

```python
class MutualRemovalService:
    """Mutual removal moderation logic"""
    
    @staticmethod
    def can_initiate_removal(
        initiator: User,
        target: User,
        discussion: Discussion
    ) -> tuple[bool, str]:
        """
        Check if initiator can remove target:
        - Both are active participants
        - Initiator hasn't already removed target in this discussion
        - Initiator hasn't initiated 3 removals already (would become permanent observer)
        - Returns: (can_remove, reason_if_not)
        """
        pass
    
    @staticmethod
    def get_removal_count(user: User, discussion: Discussion) -> int:
        """Count how many removals user has initiated in this discussion"""
        pass
    
    @staticmethod
    def get_times_removed_count(user: User, discussion: Discussion) -> int:
        """Count how many times user has been removed in this discussion"""
        pass
    
    @staticmethod
    def initiate_removal(
        initiator: User,
        target: User,
        discussion: Discussion,
        current_round: Round
    ) -> ModerationAction:
        """
        Execute mutual removal:
        1. Validate can_initiate_removal
        2. Move both initiator and target to temporary observer
        3. Set observer_reason = 'mutual_removal'
        4. Set posted_in_round_when_removed based on whether they already posted
        5. Increment initiator's removal_count
        6. Increment target's times_removed count
        7. Create ModerationAction record
        8. Check escalation rules:
           - If target's times_removed == 3: make target permanent observer
           - If initiator's removal_count == 3: make initiator permanent observer
        9. Send notifications
        10. Check if round should end (no active participants left)
        """
        pass
    
    @staticmethod
    def check_escalation(user: User, discussion: Discussion) -> str:
        """
        Check escalation status:
        - 'none': No escalation
        - 'warning': 1-2 removals, warn user
        - 'permanent': 3+ removals, permanent observer
        """
        pass
```

### 2. Notification System

#### Notification Service
Create in `core/services/notification_service.py`:

```python
class NotificationService:
    """Comprehensive notification system"""
    
    # Critical notifications (opt-out, default ON)
    CRITICAL_NOTIFICATIONS = [
        'mrp_expiring_soon',  # 25% remaining
        'moved_to_observer',
        'discussion_will_archive',  # ≤1 response warning
        'permanent_observer_warning',  # before vote-based removal
        'voting_window_closing',
        'mutual_removal_initiated',
        'mutual_removal_escalation_warning'  # approaching 3 removals
    ]
    
    # Optional notifications (opt-in, default OFF)
    OPTIONAL_NOTIFICATIONS = [
        'your_turn_reminder',  # gentle reminder to respond
        'voting_window_opened',
        'discussion_archived',
        'new_invite_received',
        'new_response_posted',
        'discussion_invite_accepted',
        'join_request_received',
        'join_request_resolved'
    ]
    
    @staticmethod
    def send_notification(
        user: User,
        notification_type: str,
        context: dict,
        delivery_methods: List[str] = ['in_app']  # in_app, email, push
    ) -> None:
        """
        Send notification to user:
        - Check user's NotificationPreference
        - If critical: always send in_app (can't disable)
        - If optional: only send if user opted in
        - Use appropriate delivery methods
        - Store in NotificationLog for in_app display
        """
        pass
    
    @staticmethod
    def create_notification_preferences(user: User) -> None:
        """
        Create default notification preferences for new user:
        - Critical notifications: enabled, in_app always
        - Optional notifications: disabled
        """
        pass
    
    @staticmethod
    def send_mrp_expiring_warning(discussion: Discussion, percentage_remaining: float) -> None:
        """Send warning at 25%, 10%, 5% MRP remaining"""
        pass
    
    @staticmethod
    def send_discussion_archive_warning(discussion: Discussion, current_round: Round) -> None:
        """Warn when ≤1 response in round (discussion will archive)"""
        pass
    
    @staticmethod
    def send_permanent_observer_warning(user: User, discussion: Discussion, votes_against: int) -> None:
        """Warn user before vote-based removal finalizes"""
        pass
    
    @staticmethod
    def send_mutual_removal_notification(initiator: User, target: User, discussion: Discussion) -> None:
        """Notify both users of mutual removal"""
        pass
    
    @staticmethod
    def send_escalation_warning(user: User, discussion: Discussion, removal_count: int) -> None:
        """Warn user approaching 3 removals (permanent observer)"""
        pass
```

#### Notification API Endpoints
Create in `core/api/notifications.py`:

**GET /api/notifications/**
```json
Response: {
  "unread_count": 5,
  "notifications": [
    {
      "id": "uuid",
      "type": "mrp_expiring_soon",
      "title": "Response time running out",
      "message": "You have 15 minutes remaining to respond in 'Should we...'",
      "context": {
        "discussion_id": "uuid",
        "round_number": 2,
        "time_remaining": "00:15:00"
      },
      "created_at": "2026-02-03T14:45:00Z",
      "read": false,
      "is_critical": true
    }
  ]
}
```

**POST /api/notifications/{notification_id}/mark-read/**
**POST /api/notifications/mark-all-read/**

**GET /api/notifications/preferences/**
```json
Response: {
  "preferences": [
    {
      "type": "mrp_expiring_soon",
      "enabled": true,
      "is_critical": true,
      "delivery_methods": {
        "in_app": true,  // always true for critical
        "email": true,
        "push": false
      }
    },
    // ... all notification types
  ]
}
```

**PATCH /api/notifications/preferences/**
```json
Request: {
  "preferences": [
    {
      "type": "new_response_posted",
      "enabled": true,
      "delivery_methods": {"in_app": true, "email": false, "push": true}
    }
  ]
}
```

### 3. Admin Dashboard & Tools

#### Admin Service
Create in `core/services/admin_service.py`:

```python
class AdminService:
    """Platform administration functionality"""
    
    @staticmethod
    def update_platform_config(admin: User, updates: dict) -> PlatformConfig:
        """
        Update platform configuration variables:
        - Validate admin permissions
        - Validate new values (types, ranges)
        - Log configuration change
        - Update PlatformConfig singleton
        """
        pass
    
    @staticmethod
    def get_platform_analytics() -> dict:
        """
        Platform health metrics:
        - Total users, active users (last 7/30 days)
        - Total discussions (active, archived)
        - Total responses, responses per user avg
        - Invites issued, invites banked
        - Moderation actions (mutual removals, vote-based removals)
        - Discussion completion rates
        - Average discussion duration/rounds
        """
        pass
    
    @staticmethod
    def flag_user(admin: User, user: User, reason: str) -> None:
        """Flag user for review (spam, abuse)"""
        pass
    
    @staticmethod
    def ban_user(admin: User, user: User, reason: str) -> None:
        """
        Ban user account:
        - Disable authentication
        - Move to permanent observer in all discussions
        - Log action
        """
        pass
    
    @staticmethod
    def verify_user_phone(admin: User, user: User) -> None:
        """Manually verify phone (for verification issues)"""
        pass
```

#### Admin API Endpoints
Create in `core/api/admin.py`:

**GET /api/admin/platform-config/**
**PATCH /api/admin/platform-config/**
```json
Request: {
  "new_user_platform_invites": 2,
  "voting_increment_percentage": 15
}
Response: {"updated": true, "config": {...}}
```

**GET /api/admin/analytics/**
```json
Response: {
  "users": {
    "total": 1234,
    "active_7_days": 456,
    "active_30_days": 789,
    "new_this_week": 45
  },
  "discussions": {
    "total": 567,
    "active": 234,
    "archived": 333,
    "avg_duration_days": 12.5,
    "avg_rounds": 8.2
  },
  "engagement": {
    "total_responses": 12345,
    "responses_per_user_avg": 10.5,
    "completion_rate": 0.67  // discussions that completed vs archived early
  },
  "moderation": {
    "mutual_removals": 123,
    "vote_based_removals": 45,
    "permanent_observers": 67
  }
}
```

**POST /api/admin/users/{user_id}/flag/**
**POST /api/admin/users/{user_id}/ban/**
**POST /api/admin/users/{user_id}/verify-phone/**

### 4. Anti-Abuse Enhancements

Update `core/security/abuse_detection.py`:

```python
class AbuseDetectionService:
    # ... existing methods from Prompt 2
    
    @staticmethod
    def detect_multi_account(user: User) -> dict:
        """
        Multi-account detection:
        - Check phone number patterns
        - Check behavioral patterns (timing, content similarity)
        - Check IP addresses (if tracked)
        - Return: {"is_likely_multi": bool, "confidence": float, "signals": []}
        """
        pass
    
    @staticmethod
    def detect_discussion_spam(user: User) -> dict:
        """
        Spam discussion creation:
        - Too many discussions created in short time
        - Duplicate/near-duplicate topics
        - No participation after creation
        """
        pass
    
    @staticmethod
    def auto_moderate(user: User) -> None:
        """
        Automatic moderation based on abuse scores:
        - High confidence spam: auto-ban
        - Medium confidence: flag for admin review
        - Rate limit aggressive users
        """
        pass
```

### 5. Basic Frontend UI (Django Templates + HTMX)

Create functional UI for core workflows:

#### Templates Structure
```
templates/
├── base.html (base template with navigation)
├── auth/
│   ├── register.html
│   ├── login.html
│   └── verify_phone.html
├── dashboard/
│   ├── home.html (user dashboard)
│   ├── invites.html
│   └── notifications.html
├── discussions/
│   ├── create.html (discussion creation wizard)
│   ├── list.html
│   ├── detail.html (discussion view with responses)
│   ├── participate.html (response submission form)
│   └── voting.html (inter-round voting UI)
├── admin/
│   ├── dashboard.html
│   ├── config.html
│   └── analytics.html
└── components/
    ├── mrp_timer.html (real-time countdown)
    ├── response_card.html
    ├── quote_selector.html
    └── notification_list.html
```

#### Key UI Features

**Discussion Creation Wizard:**
- Step 1: Topic (headline + details, character counters)
- Step 2: Pace & Style (preset buttons + custom sliders with live preview)
- Step 3: Invite Participants (search, multi-select)
- Step 4: Review & Launch (plain-language summary)

**MRP Timer Display:**
- Persistent timer (HH:MM:SS format)
- Color-coded (green > 50%, yellow 25-50%, red < 25%)
- Real-time updates via WebSocket
- Recalculation notifications

**Voting Interface:**
- Sequential presentation (parameters first, then moderation)
- Explicit vote counts: "X of Y eligible voters must agree"
- Abstention warning: "Not voting counts as 'no'"
- Countdown timer

**Moderation Safeguards:**
- Mutual removal: confirmation dialog with consequences
- Escalation badge: "X/3 removals used"
- Vote-based removal: pre-vote warning with consequences
- Removal vote: grid/gallery view of participants

**Response Editing:**
- Character budget counter: "You can change X more characters"
- Edit attempts counter: "Edit 1 of 2"
- Real-time character diff highlighting

**Orphaned Draft Protection:**
- Modal when MRP expires with unsaved text
- Options: save as draft, copy to clipboard, discard (requires confirmation)

**Use HTMX for:**
- Dynamic form updates (preset selection -> parameter preview)
- Response submission without page reload
- Voting without page reload
- Notification polling
- MRP timer updates

### 6. Background Tasks (Final Tasks)

Add to `core/tasks.py`:

```python
@shared_task
def send_daily_digest():
    """
    Daily digest email:
    - Active discussions needing response
    - Pending invites
    - Voting windows closing
    """
    pass

@shared_task
def cleanup_old_data():
    """
    Periodic cleanup:
    - Expired verification codes
    - Old notifications (> 90 days)
    - Expired invites
    """
    pass

@shared_task
def calculate_platform_health():
    """
    Daily platform health check:
    - Calculate engagement metrics
    - Detect anomalies (sudden drop in activity)
    - Alert admins if needed
    """
    pass

@shared_task
def auto_archive_abandoned_discussions():
    """
    Weekly task:
    - Find discussions with no activity for 60+ days
    - Auto-archive with reason 'abandoned'
    """
    pass
```

### 7. Comprehensive Integration Testing

Create full end-to-end tests in `tests/test_integration.py`:

#### Complete User Journeys

**Test: Complete Discussion Lifecycle**
```python
def test_full_discussion_lifecycle():
    """
    End-to-end test:
    1. User A registers (phone verification)
    2. User A earns invites by participating in existing discussion
    3. User A creates new discussion with preset
    4. User A invites Users B, C, D
    5. Round 1 Phase 1: Users respond in any order
    6. Round 1 Phase 2: MRP-regulated responses
    7. User E requests to join -> User A approves
    8. Inter-round voting: MRL increased by 10%
    9. Round 2 starts with adjusted MRL
    10. User F joins late (initial invitee)
    11. User B initiates mutual removal of User C
    12. Round 2 ends with ≤1 response -> discussion archived
    13. All responses locked
    14. Notifications sent to all participants
    """
    # Assert at each step
    # Verify database state
    # Check notification delivery
    # Validate business rules
```

**Test: Observer Reintegration Scenarios**
```python
def test_all_observer_scenarios():
    """
    Test all 5 observer reintegration scenarios:
    1. Initial invitee never participated -> joins anytime
    2. Mutual removal before posting -> rejoins same round after 1 MRP
    3. Mutual removal after posting -> rejoins next round after 1 MRP
    4. MRP expiration -> rejoins next round after 1 MRP
    5. Permanent observer -> never rejoins
    """
```

**Test: Escalation and Permanent Observer**
```python
def test_moderation_escalation():
    """
    Test escalation rules:
    1. User A removes User B (both temporary observers)
    2. User C removes User B (both temporary observers)
    3. User D removes User B (User B permanent observer, User D temporary)
    4. Verify User B's platform_invites_acquired reset to 0
    5. User A removes Users E, F, G (User A permanent observer on 3rd)
    """
```

**Test: Voting and Parameter Changes**
```python
def test_voting_parameter_changes():
    """
    Test voting mechanics:
    1. Round ends with 10 eligible voters
    2. 6 vote to increase MRL, 2 vote no change, 2 don't vote (abstain)
    3. MRL increases by 10%
    4. 5 vote to increase RTM, 5 vote no change (tie -> no change wins)
    5. RTM stays same
    6. Round 2 starts with new MRL, same RTM
    """
```

**Test: Discussion Termination Conditions**
```python
def test_all_termination_conditions():
    """
    Test each termination condition separately:
    1. Discussion with ≤1 response in round -> archived
    2. Discussion reaches max_duration_days -> archived
    3. Discussion reaches max_rounds -> archived
    4. Discussion reaches max_responses -> archived
    5. All participants become permanent observers -> archived
    """
```

#### Performance Tests

**Test: Large Discussion**
```python
def test_large_discussion_performance():
    """
    Performance test:
    - 50 participants
    - 20 rounds
    - 1000 total responses
    - Measure MRP calculation time
    - Measure response submission time
    - Measure voting resolution time
    - All operations should complete < 1 second
    """
```

**Test: Concurrent Operations**
```python
def test_concurrent_response_submission():
    """
    Test race conditions:
    - 10 users submit responses simultaneously
    - Verify MRP recalculation is atomic
    - No duplicate response numbers
    - All responses recorded correctly
    """
```

#### API Integration Tests

**Test: Complete API Workflow**
```python
def test_api_complete_workflow():
    """
    Test entire workflow via API only (no Django views):
    - Registration
    - Authentication (JWT)
    - Discussion creation
    - Response submission
    - Voting
    - Moderation
    - Notifications
    - All CRUD operations
    """
```

### 8. Documentation

Create comprehensive documentation:

**docs/API.md** - Complete API reference (auto-generated from drf-spectacular)
**docs/DEPLOYMENT.md** - Deployment instructions (Docker, environment variables)
**docs/ADMIN_GUIDE.md** - Admin dashboard usage
**docs/USER_GUIDE.md** - End-user documentation
**docs/ARCHITECTURE.md** - System architecture overview

### 9. Deployment Preparation

#### Docker Configuration
Create `Dockerfile` and `docker-compose.yml`:

```yaml
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: discussion_engine
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
  
  web:
    build: .
    command: gunicorn discussion_platform.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/discussion_engine
      - REDIS_URL=redis://redis:6379/0
  
  celery:
    build: .
    command: celery -A discussion_platform worker -l info
    depends_on:
      - db
      - redis
  
  celery-beat:
    build: .
    command: celery -A discussion_platform beat -l info
    depends_on:
      - db
      - redis

volumes:
  postgres_data:
```

#### Requirements.txt (Final)
```
Django==5.0.*
djangorestframework==3.14.*
djangorestframework-simplejwt==5.3.*
drf-spectacular==0.27.*
django-phonenumber-field==7.3.*
phonenumbers==8.13.*
psycopg2-binary==2.9.*
python-decouple==3.8
celery==5.3.*
redis==5.0.*
channels==4.0.*
channels-redis==4.1.*
twilio==8.11.*
gunicorn==21.2.*
pytest-django==4.7.*
pytest-cov==4.1.*
factory-boy==3.3.*
faker==22.0.*
black==23.12.*
flake8==7.0.*
bandit==1.7.*
```

### 10. Success Criteria

✅ Mutual removal system fully functional with escalation
✅ Notification system complete (critical and optional)
✅ In-app notifications working
✅ Email notifications configured (use console backend for dev)
✅ Admin dashboard accessible and functional
✅ Platform config updates working
✅ Analytics dashboard displaying metrics
✅ Anti-abuse detection running
✅ Frontend UI complete for all core workflows
✅ Discussion creation wizard working
✅ MRP timer displaying correctly with real-time updates
✅ Voting interface clear and functional
✅ Moderation safeguards (confirmations, warnings) working
✅ Response editing UI with character budget working
✅ Orphaned draft protection working
✅ All integration tests passing
✅ Performance tests passing (< 1s for all operations)
✅ API documentation complete
✅ Docker deployment working
✅ All tests passing (≥ 95% overall coverage)
✅ No security vulnerabilities (bandit report clean)
✅ Code formatted (black) and linted (flake8)

## Coding Standards

- Follow Django best practices for templates
- Use HTMX for progressive enhancement
- Mobile-responsive design (use TailwindCSS or Bootstrap)
- Accessibility (WCAG 2.1 AA compliance)
- Secure by default (CSRF, XSS, SQL injection prevention)
- Performance optimization (database query optimization)
- Comprehensive logging (INFO for normal operations, ERROR for issues)
- Type hints everywhere
- Docstrings for all functions
- Clean, maintainable code

## Autonomous Operation

- Install all packages automatically
- Create all migrations
- Run all tests automatically
- Generate API documentation
- Build Docker images
- Run integration tests in Docker
- Format code with black
- Lint with flake8
- Security scan with bandit
- Generate coverage reports
- NO user interaction required

## Output

Provide:
1. Complete feature summary (all features implemented)
2. Test results (total tests passed, overall coverage %)
3. Integration test results (all scenarios)
4. Performance test results (timing metrics)
5. Security scan results (bandit)
6. Docker deployment verification
7. API documentation URL
8. Final project structure
9. Deployment instructions
10. Next steps for production deployment

## Critical Notes

- This is the FINAL prompt - deliver a fully functional platform
- All features from specification must be implemented
- Integration tests are critical - they validate the entire system
- Frontend should be functional, not just beautiful
- Focus on user experience (UX requirements from spec Section 9)
- Ensure all safeguards and warnings are in place
- Docker deployment must work out of the box
- API documentation must be complete and accurate
- Performance is important - optimize database queries
- Security is paramount - run bandit and fix all issues
- Code quality matters - this should be production-ready
- Provide clear deployment instructions for production

## Post-Completion Verification Checklist

□ Register new user via phone verification
□ Create discussion using preset
□ Submit responses in Round 1
□ Observe MRP calculation and timer
□ Edit response within budget
□ Complete Round 1, enter voting
□ Vote on parameters and see results
□ Start Round 2 with adjusted parameters
□ Initiate mutual removal
□ Observe user becoming permanent observer via vote
□ Receive all critical notifications
□ Admin can update platform config
□ View analytics dashboard
□ Discussion archives on termination condition
□ All integration tests pass
□ Docker stack starts successfully
□ API documentation accessible

If all items checked: **Platform is complete and ready for production deployment!**
