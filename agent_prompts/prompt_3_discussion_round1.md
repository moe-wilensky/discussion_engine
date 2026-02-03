# Prompt 3: Discussion Creation & Round 1 Mechanics

## Objective
Implement discussion creation with UX presets, Round 1 Phase 1 & 2 mechanics, MRP calculation algorithm, response submission/editing, and quote/reference system with comprehensive testing.

## Prerequisites
✅ Prompt 1 completed: Database models exist
✅ Prompt 2 completed: Authentication and invite system working

## Context
This is the core discussion engine. Implement the complete Round 1 flow including free-form responses, MRP calculation, MRP-regulated responses, and response editing.

## Requirements

### 1. Discussion Creation Service

#### Discussion Presets
Create in `core/services/discussion_presets.py`:

```python
class DiscussionPreset:
    """Preset discussion configurations"""
    
    PRESETS = {
        "quick_exchange": {
            "name": "Quick Exchange",
            "description": "Fast-paced, brief responses",
            "mrm_minutes": 5,
            "rtm": 1.5,
            "mrl_chars": 500,
            "explanation": "Responses in ~7 minutes, up to 500 characters"
        },
        "thoughtful_discussion": {
            "name": "Thoughtful Discussion",
            "description": "Balanced pace and depth",
            "mrm_minutes": 30,
            "rtm": 2.0,
            "mrl_chars": 2000,
            "explanation": "Responses in ~60 minutes, up to 2000 characters"
        },
        "deep_dive": {
            "name": "Deep Dive",
            "description": "Slow-paced, detailed exploration",
            "mrm_minutes": 120,
            "rtm": 2.5,
            "mrl_chars": 5000,
            "explanation": "Responses in ~5 hours, up to 5000 characters"
        }
    }
    
    @staticmethod
    def get_presets() -> dict:
        """Return all presets with live previews"""
        pass
    
    @staticmethod
    def preview_parameters(mrm: int, rtm: float, mrl: int) -> dict:
        """
        Generate plain-language explanation
        Example: "If people respond every 30 minutes on average, 
                  each person will have about 60 minutes to respond."
        """
        pass
    
    @staticmethod
    def validate_parameters(mrm: int, rtm: float, mrl: int, config: PlatformConfig) -> tuple[bool, str]:
        """Validate against platform min/max bounds"""
        # Check against config.mrm_min_minutes, mrm_max_minutes
        # Check against config.rtm_min, rtm_max
        # Check against config.mrl_min_chars, mrl_max_chars
        pass
```

#### Discussion Creation Service
Create in `core/services/discussion_service.py`:

```python
class DiscussionService:
    """Core discussion business logic"""
    
    @staticmethod
    def create_discussion(
        initiator: User,
        headline: str,
        details: str,
        mrm: int,
        rtm: float,
        mrl: int,
        initial_invites: List[User]
    ) -> Discussion:
        """
        Create new discussion
        - Validate headline/details length
        - Validate parameters
        - Check duplicate (if configured)
        - Create Discussion
        - Create DiscussionParticipant for initiator (role: initiator)
        - Send invites to initial_invites
        - Create Round 1
        - Return discussion
        """
        pass
    
    @staticmethod
    def get_active_discussions(user: User) -> QuerySet:
        """Discussions where user is active participant"""
        pass
    
    @staticmethod
    def get_observable_discussions(user: User) -> QuerySet:
        """All discussions user can view"""
        pass
    
    @staticmethod
    def check_duplicate(headline: str, config: PlatformConfig) -> bool:
        """Check if duplicate discussion exists"""
        pass
```

### 2. Round 1 Implementation

#### Round Service
Create in `core/services/round_service.py`:

```python
class RoundService:
    """Round lifecycle management"""
    
    @staticmethod
    def start_round_1(discussion: Discussion) -> Round:
        """Initialize Round 1"""
        # Create Round with round_number=1, status='in_progress'
        # Set start_time
        pass
    
    @staticmethod
    def is_phase_1(round: Round, config: PlatformConfig) -> bool:
        """Check if still in Phase 1 (< N responses)"""
        # N = min(config.n_responses_before_mrp, invited_participants_count)
        pass
    
    @staticmethod
    def check_phase_1_timeout(round: Round, config: PlatformConfig) -> bool:
        """Check if Phase 1 timeout reached (30 days default)"""
        # If fewer than N responses after timeout: archive discussion
        pass
    
    @staticmethod
    def calculate_mrp(round: Round, config: PlatformConfig) -> float:
        """
        Implement MRP calculation algorithm (spec Section 5.2)
        
        Algorithm:
        1. Get response times based on mrp_calculation_scope:
           - 'current_round': times from this round only
           - 'last_X_rounds': times from previous X rounds
           - 'all_rounds': all times from all rounds
        2. Adjust times: if t < MRM, set t = MRM
        3. Calculate median of adjusted times
        4. MRP = median × RTM
        5. Minimum MRP = MRM × RTM
        
        Returns: MRP in minutes
        """
        pass
    
    @staticmethod
    def is_mrp_expired(round: Round) -> bool:
        """Check if MRP has expired since last response"""
        # Get last response time
        # Calculate MRP deadline = last_response + current_MRP
        # Return now > deadline
        pass
    
    @staticmethod
    def handle_mrp_expiration(round: Round) -> None:
        """
        When MRP expires with no response:
        - Move all non-responders to observer status
        - If ≤1 total response: archive discussion
        - Otherwise: end round, start inter-round voting
        """
        pass
    
    @staticmethod
    def should_end_round(round: Round) -> bool:
        """
        Round ends when:
        - All invited participants responded, OR
        - MRP expired with no response
        """
        pass
    
    @staticmethod
    def end_round(round: Round) -> None:
        """
        End round:
        - Set end_time
        - Calculate and store final_mrp_minutes
        - Lock all responses (is_locked = True)
        - Set status = 'voting'
        - Create inter-round voting window (Prompt 4)
        """
        pass
```

### 3. Response Submission & Editing

#### Response Service
Create in `core/services/response_service.py`:

```python
class ResponseService:
    """Response submission and editing logic"""
    
    @staticmethod
    def can_respond(user: User, round: Round) -> tuple[bool, str]:
        """
        Check if user can respond:
        - Is active participant
        - Has not responded this round
        - If returning from observer: wait period elapsed
        - Round is in_progress
        - If Phase 2: within MRP
        """
        pass
    
    @staticmethod
    def submit_response(
        user: User,
        round: Round,
        content: str
    ) -> Response:
        """
        Submit response:
        - Validate can_respond
        - Validate character count ≤ MRL
        - Calculate time_since_previous_minutes
        - Create Response
        - Recalculate MRP if Phase 2
        - Earn invites (call InviteService.earn_invite_from_response)
        - Check if round should end
        - Track first participation (if from invite)
        - Return response
        """
        pass
    
    @staticmethod
    def can_edit(user: User, response: Response, config: PlatformConfig) -> tuple[bool, str]:
        """
        Check if can edit:
        - Response belongs to user
        - Round still in_progress (not locked)
        - Edit count < config.response_edit_limit (default 2)
        - Characters changed budget remaining (20% rule)
        """
        pass
    
    @staticmethod
    def calculate_edit_budget(response: Response, config: PlatformConfig) -> int:
        """
        Calculate remaining character budget:
        - Max changeable = response.character_count * (config.response_edit_percentage / 100)
        - Already used = response.characters_changed_total
        - Remaining = max_changeable - already_used
        """
        pass
    
    @staticmethod
    def edit_response(
        user: User,
        response: Response,
        new_content: str,
        config: PlatformConfig
    ) -> Response:
        """
        Edit response:
        - Validate can_edit
        - Calculate characters changed (Levenshtein distance or simple diff)
        - Check against budget
        - Create ResponseEdit record
        - Update Response (content, last_edited_at, edit_count, characters_changed_total)
        - Return updated response
        """
        pass
    
    @staticmethod
    def save_draft(user: User, round: Round, content: str, reason: str) -> DraftResponse:
        """
        Save orphaned draft when MRP expires or round ends
        """
        pass
```

### 4. Quote/Reference System

#### Quote Service
Create in `core/services/quote_service.py`:

```python
class QuoteService:
    """Quote and reference other responses"""
    
    @staticmethod
    def create_quote(
        source_response: Response,
        quoted_text: str,
        start_index: int,
        end_index: int
    ) -> dict:
        """
        Create quote reference:
        Returns formatted quote dict:
        {
            "response_id": uuid,
            "author": username,
            "response_number": int (position in round),
            "quoted_text": str,
            "timestamp": datetime
        }
        """
        pass
    
    @staticmethod
    def format_quote_for_display(quote: dict) -> str:
        """
        Format quote for display:
        > [Username] (Response #3):
        > "The original quoted text appears here..."
        """
        pass
    
    @staticmethod
    def extract_quotes_from_content(content: str) -> List[dict]:
        """Parse content to extract embedded quotes"""
        # Parse markdown-style quotes
        # Extract metadata (response_id, author)
        pass
```

### 5. API Endpoints

Create in `core/api/discussions.py` and `core/api/responses.py`:

**GET /api/discussions/presets/**
```json
Response: {
  "presets": [
    {
      "id": "quick_exchange",
      "name": "Quick Exchange",
      "description": "...",
      "parameters": {"mrm": 5, "rtm": 1.5, "mrl": 500},
      "preview": "Responses in ~7 minutes, up to 500 characters"
    },
    // ... other presets
  ]
}
```

**POST /api/discussions/preview-parameters/**
```json
Request: {"mrm": 30, "rtm": 2.0, "mrl": 2000}
Response: {
  "valid": true,
  "preview": "If people respond every 30 minutes on average...",
  "estimated_mrp_minutes": 60
}
```

**POST /api/discussions/**
```json
Request: {
  "headline": "Should we...",
  "details": "Full topic description...",
  "preset": "thoughtful_discussion",  // OR custom parameters:
  "mrm_minutes": 30,
  "rtm": 2.0,
  "mrl_chars": 2000,
  "initial_invites": ["user_id_1", "user_id_2"]
}
Response: {
  "discussion_id": "uuid",
  "round": {"round_number": 1, "status": "in_progress", "phase": 1},
  "participants": [...]
}
```

**GET /api/discussions/{discussion_id}/**
```json
Response: {
  "id": "uuid",
  "headline": "...",
  "details": "...",
  "parameters": {"mrm": 30, "rtm": 2.0, "mrl": 2000},
  "status": "active",
  "initiator": {...},
  "participants": [...],
  "current_round": {
    "number": 1,
    "phase": 1,  // or 2
    "status": "in_progress",
    "mrp_minutes": null,  // null in Phase 1
    "mrp_deadline": null,  // when MRP expires
    "responses_count": 3,
    "responses_needed_for_phase_2": 5
  },
  "user_status": {
    "role": "active",
    "can_respond": true,
    "has_responded_this_round": false,
    "time_remaining": "HH:MM:SS",
    "can_invite": true
  }
}
```

**GET /api/discussions/{discussion_id}/rounds/{round_number}/responses/**
```json
Response: {
  "responses": [
    {
      "id": "uuid",
      "author": {"id": "uuid", "username": "..."},
      "content": "...",
      "character_count": 456,
      "created_at": "...",
      "edited_at": null,
      "edit_count": 0,
      "time_since_previous_minutes": 45.2,
      "response_number": 1,  // position in round
      "quotes": [...]  // extracted quotes
    }
  ],
  "current_mrp_minutes": 60.5,
  "mrp_deadline": "2026-02-03T14:30:00Z"
}
```

**POST /api/discussions/{discussion_id}/rounds/{round_number}/responses/**
```json
Request: {"content": "My response text..."}
Response: {
  "response": {...},
  "mrp_updated": true,
  "new_mrp_minutes": 55.3,
  "new_mrp_deadline": "...",
  "invites_earned": {"platform": 0, "discussion": 1}
}
```

**PATCH /api/responses/{response_id}/**
```json
Request: {"content": "Updated response text..."}
Response: {
  "response": {...},
  "edit_number": 1,
  "characters_changed": 87,
  "budget_remaining": 313  // 20% of 2000 = 400, used 87, remaining 313
}
```

**POST /api/responses/{response_id}/save-draft/**
```json
Request: {"content": "...", "reason": "mrp_expired"}
Response: {"draft_id": "uuid", "message": "Draft saved"}
```

**POST /api/responses/{response_id}/quote/**
```json
Request: {
  "quoted_text": "selected text",
  "start_index": 0,
  "end_index": 50
}
Response: {
  "quote_markdown": "> [Username] (Response #3):\n> \"selected text\""
}
```

### 6. Real-Time MRP Updates

Create WebSocket consumer in `core/consumers.py`:

```python
class DiscussionConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for real-time discussion updates
    - New responses posted
    - MRP recalculated
    - Round status changes
    - MRP expiration warnings
    """
    
    async def connect(self):
        # Join discussion channel
        pass
    
    async def new_response(self, event):
        # Broadcast: new response, updated MRP
        pass
    
    async def mrp_warning(self, event):
        # Broadcast: MRP expiring soon (25%, 10%, 5%)
        pass
    
    async def round_ended(self, event):
        # Broadcast: round ended, voting starts
        pass
```

Configure Django Channels with Redis backend.

### 7. Background Tasks (Celery)

Create in `core/tasks.py`:

```python
@shared_task
def check_mrp_expirations():
    """
    Periodic task (every minute):
    - Find all in_progress rounds
    - Check if MRP expired
    - Call RoundService.handle_mrp_expiration
    """
    pass

@shared_task
def check_phase_1_timeouts():
    """
    Daily task:
    - Find Round 1 Phase 1 discussions
    - Check if 30 days elapsed
    - Archive if < N responses
    """
    pass

@shared_task
def send_mrp_warning(discussion_id, percentage_remaining):
    """
    Send warning when MRP at 25%, 10%, 5% remaining
    """
    pass

@shared_task
def send_single_response_warning(discussion_id):
    """
    When round has only 1 response, warn about archival
    """
    pass
```

### 8. Automated Testing

Create comprehensive tests:

#### `test_discussion_creation.py`
- ✅ Create discussion with preset
- ✅ Create discussion with custom parameters
- ✅ Parameter validation (min/max bounds)
- ✅ Headline/details length validation
- ✅ Duplicate discussion detection (when enabled)
- ✅ Initial invites sent correctly
- ✅ Round 1 created automatically

#### `test_round_1_phase_1.py`
- ✅ Free-form response order (any order)
- ✅ Time tracking between responses
- ✅ Phase 1 -> Phase 2 transition at N responses
- ✅ N adjustment when invited < n_responses_before_mrp
- ✅ Phase 1 timeout (30 days)
- ✅ Discussion archived if < N responses after timeout

#### `test_round_1_phase_2.py`
- ✅ MRP calculation algorithm (multiple scenarios)
- ✅ MRP recalculation after each response
- ✅ MRP scope configuration (current_round, last_X_rounds, all_rounds)
- ✅ Response within MRP allowed
- ✅ Response after MRP expires rejected
- ✅ Non-responders moved to observer when MRP expires
- ✅ Round ends when all participants respond
- ✅ Round ends when MRP expires with no response

#### `test_mrp_algorithm.py`
- ✅ Example from spec: [10, 60, 40] with MRM=30, RTM=2 -> MRP=80
- ✅ Dynamic recalculation: add t₄=20 -> MRP=70
- ✅ Minimum MRP = MRM × RTM
- ✅ Median calculation with even/odd number of times
- ✅ All times < MRM (should all become MRM)
- ✅ Large dataset (100+ responses)

#### `test_response_editing.py`
- ✅ Edit response within 20% budget
- ✅ Edit count limit (2 edits max)
- ✅ Budget calculation correct
- ✅ Can't edit after budget exhausted
- ✅ Can't edit after round ends (locked)
- ✅ ResponseEdit record created
- ✅ Character change calculation (use difflib)

#### `test_quote_system.py`
- ✅ Create quote from response
- ✅ Format quote markdown
- ✅ Extract quotes from content
- ✅ Multiple quotes in one response
- ✅ Quote navigation (response_id reference)

#### `test_draft_responses.py`
- ✅ Save draft when MRP expires
- ✅ Save draft when round ends
- ✅ Retrieve drafts
- ✅ Draft doesn't affect round state

#### `test_api_discussions.py`
- ✅ Full discussion creation flow (API)
- ✅ Submit responses in Phase 1
- ✅ Submit responses in Phase 2
- ✅ Edit response via API
- ✅ MRP recalculation via API
- ✅ Quote response via API
- ✅ WebSocket updates received

#### Test Coverage Target: ≥ 95% for discussion/round/response services

### 9. Success Criteria

✅ Discussion creation working with all presets
✅ Custom parameter validation working
✅ Round 1 Phase 1 complete (free-form responses)
✅ Round 1 Phase 2 complete (MRP-regulated)
✅ MRP calculation algorithm verified against spec examples
✅ MRP recalculation after each response working
✅ Response editing with 20% budget working
✅ Quote system functional
✅ Draft saving on MRP expiration working
✅ Phase 1 timeout (30 days) working
✅ Observer status on MRP expiration working
✅ All API endpoints functional
✅ WebSocket real-time updates working
✅ All tests passing (≥95% coverage)
✅ Celery tasks running correctly
✅ No performance issues with MRP calculation

## Coding Standards

- Use Django select_related/prefetch_related for queries
- Cache MRP calculations (Redis) to avoid repeated computation
- Use database transactions for round state changes
- Add logging for all state transitions
- Validate all inputs at service layer
- Use atomic operations for concurrent response submissions
- Handle race conditions (multiple simultaneous responses)
- Type hints for all service methods
- Comprehensive docstrings with examples

## Autonomous Operation

- Install Channels and Redis automatically
- Create all migrations
- Run all tests automatically
- Start Celery worker and beat
- Start Channels/WebSocket server for tests
- Mock time-dependent tests (freezegun)
- NO user interaction required

## Output

Provide:
1. Services and endpoints created
2. Test results (passed, coverage %)
3. MRP algorithm verification (show example calculations)
4. WebSocket connection test results
5. Performance metrics (MRP calculation time)
6. Next steps for Prompt 4

## Critical Notes

- MRP calculation is CORE to the platform - test exhaustively
- Handle timezone-aware datetimes correctly
- Use Celery beat for periodic MRP expiration checks
- WebSocket updates must be real-time (< 1 second delay)
- Quote system must preserve context (author, response number)
- Draft saving prevents user frustration - implement carefully
- Phase 1 timeout prevents abandoned discussions
- Test with concurrent users (simulate race conditions)
- Document MRP algorithm with examples in code comments
