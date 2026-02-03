# Prompt 1: Project Foundation & Database Architecture

## Objective
Initialize a Django project for the Discussion Engine platform with complete database models, configuration system, and automated testing. This is the foundation that all subsequent prompts will build upon.

## Context
You are building a discussion platform that enables structured, time-regulated conversations. This prompt establishes the core data architecture and project structure.

## Requirements

### 1. Project Initialization
- Create Django project named `discussion_platform` in the current directory
- Work exclusively within the existing `.venv` virtual environment
- Install all required packages within `.venv`:
  - Django 5.0+
  - djangorestframework
  - psycopg2-binary (PostgreSQL adapter)
  - python-decouple (for environment variables)
  - pytest-django
  - pytest-cov
  - factory-boy (for test fixtures)
  - faker (for test data)
- Configure PostgreSQL database connection (use environment variables)
- Enable Django REST Framework
- Set up pytest configuration for Django

### 2. Database Models (Complete Architecture)

Create all models in `discussion_platform/core/models.py`:

#### User Extension
```python
# Extend Django User model with:
- phone_number (unique, required)
- platform_invites_acquired (default 0)
- platform_invites_used (default 0)
- platform_invites_banked (default 0)
- discussion_invites_acquired (default 0)
- discussion_invites_used (default 0)
- discussion_invites_banked (default 0)
- is_platform_admin (default False)
- behavioral_flags (JSONField, default {})
- account_deletion_preference (choices: delete_all, preserve_data)
- created_at, updated_at
```

#### PlatformConfig (Singleton)
All configuration variables from specification Section 4:
- new_user_platform_invites, new_user_discussion_invites
- responses_to_unlock_invites
- responses_per_platform_invite, responses_per_discussion_invite
- max_discussion_participants
- n_responses_before_mrp
- max_headline_length, max_topic_length
- invite_consumption_trigger (choices: 'sent', 'accepted')
- mrp_calculation_scope (choices: 'current_round', 'last_X_rounds', 'all_rounds')
- voting_increment_percentage
- vote_based_removal_threshold
- max_discussion_duration_days, max_discussion_rounds, max_discussion_responses
- round_1_phase_1_timeout_days
- allow_duplicate_discussions
- response_edit_percentage, response_edit_limit
- rtm_min, rtm_max
- mrm_min_minutes, mrm_max_minutes
- mrl_min_chars, mrl_max_chars

#### Discussion
- topic_headline (CharField, max_length from config)
- topic_details (TextField, max_length from config)
- max_response_length_chars (IntegerField, MRL)
- response_time_multiplier (FloatField, RTM)
- min_response_time_minutes (IntegerField, MRM)
- status (choices: 'active', 'archived')
- initiator (FK to User)
- delegated_approver (FK to User, null=True)
- created_at, archived_at

#### DiscussionParticipant
- discussion (FK to Discussion)
- user (FK to User)
- role (choices: 'initiator', 'active', 'temporary_observer', 'permanent_observer')
- joined_at
- observer_since (DateTimeField, null=True)
- observer_reason (choices: null, 'mrp_expired', 'mutual_removal', 'vote_based_removal')
- posted_in_round_when_removed (BooleanField, default False)
- removal_count (IntegerField, default 0) - mutual removals initiated
- can_invite_others (BooleanField, default True)
- Unique constraint: (discussion, user)

#### Round
- discussion (FK to Discussion)
- round_number (IntegerField, indexed)
- start_time
- end_time (null=True)
- final_mrp_minutes (FloatField, null=True)
- status (choices: 'in_progress', 'voting', 'completed')
- Unique constraint: (discussion, round_number)

#### Response
- round (FK to Round)
- user (FK to User)
- content (TextField)
- character_count (IntegerField)
- created_at
- last_edited_at (null=True)
- edit_count (IntegerField, default 0)
- characters_changed_total (IntegerField, default 0)
- time_since_previous_minutes (FloatField, null=True)
- is_locked (BooleanField, default False)

#### Vote (Inter-round parameter voting)
- round (FK to Round)
- user (FK to User)
- mrl_vote (choices: 'increase', 'no_change', 'decrease')
- rtm_vote (choices: 'increase', 'no_change', 'decrease')
- voted_at
- Unique constraint: (round, user)

#### RemovalVote (Vote-based moderation)
- round (FK to Round)
- voter (FK to User)
- target (FK to User)
- voted_at

#### ModerationAction
- discussion (FK to Discussion)
- action_type (choices: 'mutual_removal', 'vote_based_removal')
- initiator (FK to User)
- target (FK to User)
- round_occurred (FK to Round)
- is_permanent (BooleanField)
- action_at

#### Invite
- inviter (FK to User)
- invitee (FK to User, null=True)
- invite_type (choices: 'platform', 'discussion')
- discussion (FK to Discussion, null=True)
- status (choices: 'sent', 'accepted', 'declined', 'expired')
- sent_at
- accepted_at (null=True)
- first_participation_at (null=True)

#### JoinRequest
- discussion (FK to Discussion)
- requester (FK to User)
- approver (FK to User)
- status (choices: 'pending', 'approved', 'declined')
- request_message (TextField, blank=True)
- response_message (TextField, blank=True)
- created_at
- resolved_at (null=True)

#### ResponseEdit
- response (FK to Response)
- edit_number (IntegerField, choices: 1, 2)
- previous_content (TextField)
- new_content (TextField)
- characters_changed (IntegerField)
- edited_at

#### DraftResponse
- discussion (FK to Discussion)
- round (FK to Round)
- user (FK to User)
- content (TextField)
- created_at
- saved_reason (choices: 'mrp_expired', 'user_saved', 'round_ended')

#### NotificationPreference
- user (FK to User)
- notification_type (choices: see spec Section 8)
- enabled (BooleanField, default varies by type)
- delivery_method (JSONField: {email: bool, push: bool, in_app: bool})

### 3. Database Indexes
Add all critical indexes from specification Section 16:
- DiscussionParticipant: (discussion_id, user_id), (user_id, role), (observer_since, observer_reason)
- Round: (discussion_id, round_number), (status)
- Response: (round_id, user_id), (created_timestamp)
- Vote: (round_id, user_id)
- RemovalVote: (round_id, voter_id), (round_id, target_id)
- Invite: (inviter_id, status), (invitee_id, status)
- JoinRequest: (discussion_id, status), (requester_id, status)

### 4. Model Methods & Properties

Add essential model methods:

**User model:**
- `can_send_platform_invite()` -> bool
- `can_send_discussion_invite()` -> bool
- `earn_invite(invite_type)` -> void
- `consume_invite(invite_type)` -> void

**Discussion model:**
- `is_at_participant_cap()` -> bool
- `get_active_participants()` -> QuerySet
- `should_archive()` -> bool, reason

**Round model:**
- `calculate_mrp(config)` -> float (minutes)
- `is_expired()` -> bool
- `get_response_times()` -> List[float]

**DiscussionParticipant model:**
- `can_rejoin()` -> bool
- `get_wait_period_end()` -> datetime

### 5. Automated Testing

Create comprehensive tests in `tests/test_models.py`:

#### Test Coverage Requirements:
- ✅ All model creation and validation
- ✅ User invite tracking (acquired = used + banked)
- ✅ PlatformConfig singleton behavior
- ✅ Discussion participant role transitions
- ✅ Observer reentry logic (all 4 scenarios from spec Section 5.3)
- ✅ Invite consumption triggers
- ✅ Response edit limits (20% rule, 2 edit max)
- ✅ MRP calculation algorithm (see spec Section 5.2)
- ✅ Round status transitions
- ✅ Vote counting and majority logic
- ✅ Moderation action tracking
- ✅ All unique constraints and indexes
- ✅ Edge cases: duplicate discussions, participant caps, removal escalation

#### Test Data:
- Use factory_boy for model factories
- Use faker for realistic test data
- Create fixtures for common scenarios

#### Test Execution:
- All tests must pass with 100% model coverage
- Run: `pytest --cov=discussion_platform/core/models --cov-report=html`
- Generate coverage report automatically

### 6. Django Admin Configuration

Create `admin.py` with:
- ModelAdmin for all models
- Inline editing for related models
- List filters, search fields
- Read-only fields for calculated values
- Custom actions for common admin tasks

### 7. Project Structure

```
discussion_platform/
├── manage.py
├── discussion_platform/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/
│   ├── models.py (all models)
│   ├── admin.py
│   ├── apps.py
│   └── migrations/
├── tests/
│   ├── __init__.py
│   ├── conftest.py (pytest fixtures)
│   ├── factories.py (factory_boy)
│   └── test_models.py
├── pytest.ini
├── requirements.txt
└── .env.example
```

### 8. Configuration Files

**pytest.ini:**
```ini
[pytest]
DJANGO_SETTINGS_MODULE = discussion_platform.settings
python_files = tests.py test_*.py *_tests.py
addopts = --reuse-db --cov=discussion_platform --cov-report=html --cov-report=term-missing
```

**.env.example:**
```
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_NAME=discussion_engine
DATABASE_USER=postgres
DATABASE_PASSWORD=password
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

### 9. Success Criteria

✅ All migrations created and applied successfully
✅ All models created with proper fields, constraints, and indexes
✅ PlatformConfig populated with default values
✅ All tests passing (pytest shows green)
✅ Test coverage ≥ 95% for models
✅ Django admin accessible and functional
✅ No import errors or warnings
✅ Database queries optimized (select_related, prefetch_related where needed)
✅ Code follows PEP 8 (run `black` formatter)
✅ Type hints added to all model methods

## Coding Standards

- Follow Django best practices and naming conventions
- Use Django ORM efficiently (avoid N+1 queries)
- Add docstrings to all models and methods
- Use type hints (Python 3.10+)
- Format code with `black`
- Validate with `flake8`
- All datetime handling in UTC
- Use Django's timezone-aware datetime

## Autonomous Operation

- Install all packages automatically within `.venv`
- Create database migrations automatically
- Run migrations automatically
- Create and run all tests automatically
- Generate coverage reports automatically
- Fix any linting issues automatically
- NO user input required except initial database credentials in .env

## Output

Provide:
1. Complete file structure created
2. Summary of all models created (count, relationships)
3. Test results (number passed, coverage percentage)
4. Any warnings or issues encountered
5. Next steps for Prompt 2

## Critical Notes

- This is FOUNDATION ONLY - no API endpoints, no views, no frontend
- Focus on robust data architecture and testing
- All business logic from specification must be testable at model level
- Subsequent prompts will build authentication, APIs, and UI on this foundation
- Ensure migrations are clean and reversible
- Document any assumptions made in code comments
