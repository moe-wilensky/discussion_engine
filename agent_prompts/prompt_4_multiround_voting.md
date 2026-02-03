# Prompt 4: Multi-Round System, Voting & Observer Reintegration

## Objective
Implement inter-round voting (parameter and moderation voting), Round 2+ mechanics with MRP inheritance, observer reintegration with nuanced rules, and discussion termination conditions with comprehensive testing.

## Prerequisites
✅ Prompt 1 completed: Database models exist
✅ Prompt 2 completed: Authentication and invites working
✅ Prompt 3 completed: Discussion creation and Round 1 working

## Context
Build the complete multi-round discussion lifecycle including inter-round voting, parameter adjustments, observer reintegration logic, and all termination conditions.

## Requirements

### 1. Inter-Round Voting System

#### Voting Service
Create in `core/services/voting_service.py`:

```python
class VotingService:
    """Inter-round voting logic"""
    
    @staticmethod
    def start_voting_window(round: Round) -> None:
        """
        After round ends:
        - Set round.status = 'voting'
        - Voting window duration = round.final_mrp_minutes
        - Create Vote records for eligible voters (initiator + active participants from round)
        - Send notifications
        """
        pass
    
    @staticmethod
    def get_eligible_voters(round: Round) -> QuerySet[User]:
        """
        Eligible voters:
        - Discussion initiator
        - All active participants who responded in this round
        """
        pass
    
    @staticmethod
    def cast_parameter_vote(
        user: User,
        round: Round,
        mrl_vote: str,  # 'increase', 'no_change', 'decrease'
        rtm_vote: str
    ) -> Vote:
        """
        Cast vote for parameter changes
        - Validate user is eligible voter
        - Create or update Vote record
        - Return vote
        """
        pass
    
    @staticmethod
    def count_votes(round: Round, parameter: str) -> dict:
        """
        Count votes for a parameter (mrl or rtm)
        Returns: {
            'increase': count,
            'no_change': count,
            'decrease': count,
            'not_voted': count,
            'total_eligible': count,
            'majority_needed': count  # ceil(total_eligible / 2) + 1
        }
        """
        pass
    
    @staticmethod
    def resolve_vote(round: Round, parameter: str) -> str:
        """
        Resolve vote (simple majority of eligible voters, not just those who voted)
        - Abstentions count as 'no_change'
        - Ties (50/50) -> 'no_change' wins
        - Returns: 'increase', 'no_change', 'decrease'
        """
        pass
    
    @staticmethod
    def apply_parameter_change(
        discussion: Discussion,
        parameter: str,  # 'mrl' or 'rtm'
        change: str,  # 'increase', 'no_change', 'decrease'
        config: PlatformConfig
    ) -> None:
        """
        Apply voted parameter change
        - Get increment percentage from config.voting_increment_percentage (default 10%)
        - Calculate new value
        - Validate against min/max bounds
        - Update discussion
        """
        pass
    
    @staticmethod
    def close_voting_window(round: Round, config: PlatformConfig) -> None:
        """
        After voting window expires:
        - Count votes for MRL
        - Count votes for RTM
        - Resolve each vote
        - Apply parameter changes
        - Create next round
        - Update round.status = 'completed'
        """
        pass
```

#### Moderation Voting Service
Create in `core/services/moderation_voting_service.py`:

```python
class ModerationVotingService:
    """Vote-based removal system"""
    
    @staticmethod
    def get_eligible_targets(round: Round) -> QuerySet[User]:
        """
        All active participants in round (excluding voter themselves when casting)
        """
        pass
    
    @staticmethod
    def cast_removal_vote(
        voter: User,
        round: Round,
        targets: List[User]
    ) -> List[RemovalVote]:
        """
        Cast vote to remove one or more users
        - Validate voter is eligible (active participant in round)
        - Can vote for multiple targets
        - Create RemovalVote records
        - Returns list of votes cast
        """
        pass
    
    @staticmethod
    def count_removal_votes(round: Round, target: User) -> dict:
        """
        Count votes against a target
        Returns: {
            'votes_for_removal': count,
            'total_eligible_voters': count,
            'percentage': float,
            'threshold': float,  # from config.vote_based_removal_threshold
            'will_be_removed': bool
        }
        """
        pass
    
    @staticmethod
    def resolve_removal_votes(round: Round, config: PlatformConfig) -> List[User]:
        """
        After voting window:
        - For each active participant
        - Count votes against them
        - If votes >= threshold (default 80% of eligible voters): permanent observer
        - Reset platform_invites_acquired to 0 for removed users
        - Update DiscussionParticipant role to 'permanent_observer'
        - Log ModerationAction
        - Send notifications
        - Returns list of removed users
        """
        pass
```

### 2. Round 2+ Mechanics

#### Multi-Round Service
Create in `core/services/multi_round_service.py`:

```python
class MultiRoundService:
    """Round 2+ lifecycle management"""
    
    @staticmethod
    def create_next_round(discussion: Discussion, previous_round: Round) -> Round:
        """
        Create next round:
        - Increment round_number
        - Inherit final_mrp_minutes from previous round (or adjusted if RTM changed)
        - Set status = 'in_progress'
        - MRP regulation applies from first response (no Phase 1)
        - Active participants = previous active + any newly invited - any removed
        """
        pass
    
    @staticmethod
    def check_termination_conditions(discussion: Discussion, round: Round, config: PlatformConfig) -> tuple[bool, str]:
        """
        Check if discussion should be archived:
        1. Round received ≤1 response
        2. max_discussion_duration_days reached (if > 0)
        3. max_discussion_rounds reached (if > 0)
        4. max_discussion_responses reached (if > 0)
        5. All active participants became permanent observers
        
        Returns: (should_archive, reason)
        """
        pass
    
    @staticmethod
    def archive_discussion(discussion: Discussion, reason: str) -> None:
        """
        Archive discussion:
        - Set status = 'archived'
        - Set archived_at timestamp
        - Lock all responses across all rounds
        - Send notifications
        - Log archival reason
        """
        pass
```

### 3. Observer Reintegration (Nuanced Rules)

#### Observer Service
Create in `core/services/observer_service.py`:

```python
class ObserverService:
    """Complex observer reintegration logic"""
    
    @staticmethod
    def move_to_observer(
        participant: DiscussionParticipant,
        reason: str,
        posted_in_round: bool = False
    ) -> None:
        """
        Move user to observer status:
        - Update role to 'temporary_observer'
        - Set observer_since = now
        - Set observer_reason
        - Set posted_in_round_when_removed
        """
        pass
    
    @staticmethod
    def can_rejoin(participant: DiscussionParticipant, current_round: Round) -> tuple[bool, str]:
        """
        Implement nuanced reentry rules (spec Section 5.3):
        
        1. Initial invitees who never participated: Can join anytime (return True, "")
        
        2. Moved to observer via mutual removal BEFORE posting in current round:
           - Can rejoin same round after 1 MRP has elapsed from removal time
           - Only if round still active
           
        3. Moved to observer via mutual removal AFTER posting in current round:
           - Must wait until 1 MRP has elapsed in NEXT round
           
        4. Moved to observer due to MRP expiration (didn't post in round):
           - Must wait until 1 MRP has elapsed in NEXT round
           
        5. Permanent observer: Never (return False, "permanent")
        
        Returns: (can_rejoin, reason_if_not)
        """
        pass
    
    @staticmethod
    def get_wait_period_end(participant: DiscussionParticipant, current_round: Round) -> datetime:
        """
        Calculate when observer can rejoin based on nuanced rules
        """
        pass
    
    @staticmethod
    def rejoin_as_active(participant: DiscussionParticipant) -> None:
        """
        Return observer to active status:
        - Validate can_rejoin
        - Update role to 'active'
        - Clear observer_since, observer_reason
        """
        pass
    
    @staticmethod
    def make_permanent_observer(
        participant: DiscussionParticipant,
        reason: str
    ) -> None:
        """
        Permanent observer status:
        - Update role to 'permanent_observer'
        - Set observer_reason
        - Reset user.platform_invites_acquired = 0
        - Reset user.platform_invites_banked = 0
        - Log consequence
        """
        pass
```

### 4. API Endpoints

Create in `core/api/voting.py` and update `core/api/discussions.py`:

**GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/status/**
```json
Response: {
  "voting_window_open": true,
  "window_closes_at": "2026-02-03T15:00:00Z",
  "time_remaining": "HH:MM:SS",
  "user_is_eligible": true,
  "user_has_voted_parameters": false,
  "user_has_voted_removal": false,
  "eligible_voters_count": 10,
  "votes_cast_count": 6
}
```

**GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/parameter-results/**
```json
Response: {
  "mrl": {
    "increase": 3,
    "no_change": 2,
    "decrease": 1,
    "not_voted": 4,
    "total_eligible": 10,
    "majority_needed": 6,
    "current_winner": "no_change",  // abstentions count as no_change
    "will_pass": false
  },
  "rtm": {...}
}
```

**POST /api/discussions/{discussion_id}/rounds/{round_number}/voting/parameters/**
```json
Request: {
  "mrl_vote": "increase",  // or "no_change", "decrease"
  "rtm_vote": "no_change"
}
Response: {
  "vote_recorded": true,
  "current_results": {...}
}
```

**GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/removal-targets/**
```json
Response: {
  "eligible_targets": [
    {
      "user_id": "uuid",
      "username": "...",
      "responses_this_round": 1,
      "invite_metrics": {...}
    }
  ]
}
```

**POST /api/discussions/{discussion_id}/rounds/{round_number}/voting/removal/**
```json
Request: {
  "target_user_ids": ["uuid1", "uuid2"]  // can vote for multiple
}
Response: {
  "votes_cast": 2,
  "message": "Removal votes recorded"
}
```

**GET /api/discussions/{discussion_id}/rounds/{round_number}/voting/removal-results/**
```json
Response: {
  "targets": [
    {
      "user_id": "uuid",
      "username": "...",
      "votes_for_removal": 8,
      "total_eligible": 10,
      "percentage": 80,
      "threshold": 80,
      "will_be_removed": true
    }
  ]
}
```

**GET /api/discussions/{discussion_id}/observer-status/**
```json
Response: {
  "user_role": "temporary_observer",
  "observer_since": "2026-02-02T10:00:00Z",
  "observer_reason": "mutual_removal",
  "posted_before_removal": false,
  "can_rejoin": false,
  "can_rejoin_at": "2026-02-02T11:00:00Z",  // after 1 MRP
  "current_round": 3,
  "can_rejoin_in_round": 3  // or 4 depending on scenario
}
```

**POST /api/discussions/{discussion_id}/rejoin/**
```json
Request: {}
Response: {
  "rejoined": true,
  "new_role": "active",
  "current_round": 3
}
```

### 5. Background Tasks (Celery)

Add to `core/tasks.py`:

```python
@shared_task
def close_voting_windows():
    """
    Periodic task (every minute):
    - Find rounds with status='voting' where window expired
    - Call VotingService.close_voting_window
    - Call ModerationVotingService.resolve_removal_votes
    - Create next round or archive discussion
    """
    pass

@shared_task
def check_discussion_termination():
    """
    Periodic task (hourly):
    - Check all active discussions for termination conditions
    - Archive if conditions met
    """
    pass

@shared_task
def send_voting_window_closing_warning(round_id, time_remaining):
    """Send warning when voting window closing soon"""
    pass

@shared_task
def send_removal_warning(user_id, discussion_id, votes_against, threshold):
    """Warn user they may be removed"""
    pass

@shared_task
def send_permanent_observer_notification(user_id, discussion_id, consequence):
    """Notify user of permanent observer consequences"""
    pass
```

### 6. Automated Testing

Create comprehensive tests:

#### `test_voting_parameters.py`
- ✅ Eligible voters correct (initiator + active participants)
- ✅ Cast parameter vote (MRL, RTM)
- ✅ Vote counting correct
- ✅ Simple majority calculation
- ✅ Abstention = no_change vote
- ✅ Tie (50/50) = no_change wins
- ✅ Apply parameter increase (10% increment)
- ✅ Apply parameter decrease (10% decrement)
- ✅ Parameter bounds validation (min/max)
- ✅ Voting window expiration
- ✅ Multiple separate votes (MRL and RTM independent)

#### `test_voting_removal.py`
- ✅ Cast removal vote for single target
- ✅ Cast removal vote for multiple targets
- ✅ Vote counting per target
- ✅ Super-majority threshold (80%)
- ✅ Target becomes permanent observer
- ✅ Platform invites reset to 0
- ✅ Multiple users removed simultaneously
- ✅ Removal notifications sent
- ✅ Hidden ballot (votes not visible until resolved)

#### `test_observer_reintegration.py`
- ✅ **Scenario 1**: Initial invitee never participated -> can join anytime
- ✅ **Scenario 2**: Mutual removal before posting -> rejoin same round after 1 MRP
- ✅ **Scenario 3**: Mutual removal after posting -> rejoin next round after 1 MRP
- ✅ **Scenario 4**: MRP expiration -> rejoin next round after 1 MRP
- ✅ **Scenario 5**: Permanent observer -> never rejoin
- ✅ Wait period calculation correct
- ✅ Rejoin at correct time allowed
- ✅ Rejoin before wait period rejected

#### `test_round_2_plus.py`
- ✅ Create Round 2 after voting
- ✅ Inherit MRP from Round 1
- ✅ Adjusted MRP if RTM changed
- ✅ No Phase 1 in Round 2+
- ✅ MRP regulation from first response
- ✅ Active participants updated correctly
- ✅ Round 3, 4, 5... (test multiple rounds)

#### `test_termination_conditions.py`
- ✅ Archive when ≤1 response in round
- ✅ Archive when max_duration_days reached
- ✅ Archive when max_rounds reached
- ✅ Archive when max_responses reached
- ✅ Archive when all participants permanent observers
- ✅ Archival reason logged correctly
- ✅ All responses locked on archive
- ✅ Notifications sent

#### `test_api_voting.py`
- ✅ Full voting flow via API
- ✅ Parameter voting and resolution
- ✅ Removal voting and resolution
- ✅ Observer status API
- ✅ Rejoin API

#### Test Coverage Target: ≥ 95% for voting and observer services

### 7. WebSocket Updates

Add to `core/consumers.py`:

```python
class DiscussionConsumer(AsyncWebsocketConsumer):
    # ... existing methods
    
    async def voting_started(self, event):
        """Broadcast: voting window opened"""
        pass
    
    async def voting_updated(self, event):
        """Broadcast: new vote cast, updated counts"""
        pass
    
    async def voting_closed(self, event):
        """Broadcast: voting window closed, results"""
        pass
    
    async def parameter_changed(self, event):
        """Broadcast: MRL or RTM changed"""
        pass
    
    async def user_removed(self, event):
        """Broadcast: user became permanent observer"""
        pass
    
    async def next_round_started(self, event):
        """Broadcast: new round created"""
        pass
    
    async def discussion_archived(self, event):
        """Broadcast: discussion archived, reason"""
        pass
```

### 8. Success Criteria

✅ Inter-round voting system fully functional
✅ Parameter voting (MRL, RTM) with independent votes
✅ Vote counting and majority calculation correct
✅ Abstention = no_change logic working
✅ Tie handling correct (status quo maintained)
✅ Parameter changes applied correctly (10% increment)
✅ Parameter bounds validation working
✅ Removal voting system functional
✅ Super-majority threshold (80%) enforced
✅ Multiple simultaneous removals working
✅ Permanent observer status applied correctly
✅ Platform invites reset for permanent observers
✅ Observer reintegration - all 5 scenarios working correctly
✅ Wait period calculations accurate
✅ Round 2+ creation and MRP inheritance working
✅ All termination conditions working
✅ Discussion archival complete
✅ All API endpoints functional
✅ WebSocket updates for all events
✅ All tests passing (≥95% coverage)
✅ Celery tasks running correctly

## Coding Standards

- Use database transactions for voting resolution
- Handle concurrent voting (atomic operations)
- Validate all voter eligibility at service layer
- Log all moderation actions
- Use select_related for voter queries
- Cache vote counts (invalidate on new vote)
- Type hints for all service methods
- Comprehensive docstrings with examples
- Test all edge cases (ties, exactly at threshold, etc.)

## Autonomous Operation

- Install any additional packages needed
- Create all migrations
- Run all tests automatically
- Start Celery worker and beat
- Mock time-dependent tests (freezegun)
- NO user interaction required

## Output

Provide:
1. Services and endpoints created
2. Test results (passed, coverage %)
3. Observer reintegration scenario test results (all 5 scenarios)
4. Voting logic verification (show example calculations)
5. Termination condition test results
6. Next steps for Prompt 5

## Critical Notes

- Observer reintegration has 5 distinct scenarios - test each thoroughly
- Voting resolution must handle abstentions correctly (count as no_change)
- Tie votes (50/50) maintain status quo
- Super-majority threshold is configurable but defaults to 80%
- Permanent observer consequences are severe - warn users clearly
- Platform invites reset is automatic and irreversible
- Parameter changes must respect min/max bounds
- Round 2+ has no Phase 1 - MRP applies from first response
- Termination conditions are checked in order (first match triggers archive)
- All responses must be locked on archive
- Test with many rounds (10+ rounds) to ensure stability
