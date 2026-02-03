# Discussion Engine - Technical Specification

## 1. PROJECT OVERVIEW

The discussion engine is a platform designed to foster structured discussion and collaboration among diverse individuals through iterative, time-regulated conversation rounds.

### Core Principles

1. **Public Observation, Controlled Participation**: All discussions are publicly viewable, but active participation requires invitation
2. **Iterative Discussion**: All discussion proceeds through structured rounds where invited users provide input
3. **Dynamic Time Management**: Response time limits adjust automatically based on participant behavior and can be manually configured
4. **Community-Based Moderation**: Users perform moderation actions with built-in mechanisms to encourage reintegration of moderated participants

---

## 2. USER SYSTEM

### User Onboarding
- All users must be invited by an existing platform user
- Users can only join the platform once (enforced via phone number verification + behavioral analysis for spam/multi-account detection)
- New users receive starting allocation of platform invites and discussion invites after completing a configurable number of responses (can be set to 0 for immediate access)
- Account deletion: Users can choose to delete all data or preserve it associated with their ID for potential future rejoining

### User Capabilities
- **Any user can**: Start a discussion topic, observe any discussion
- **Discussion participation**: Users can only join active discussion after invitation from either:
  - The discussion initiator, OR
  - An active participant in that discussion

### User Roles (per discussion)
- **Initiator**: Started the discussion, has authority to approve uninvited users (this authority can be delegated to another active participant)
- **Active Participant**: Currently participating in discussion rounds
- **Observer**: Can view but not respond (permanent or temporary status); cannot send private messages to active participants

---

## 3. INVITE SYSTEM

### Invite Types
1. **Platform Invites**: Used to invite new users to the platform (more limited)
2. **Discussion Invites**: Used to invite users to join specific discussions

### Earning Invites
- Users earn invites by submitting responses in discussions (1 round = 1 response per user)
- Invites required per type:
  - Platform invite: Requires N₁ responses (configurable)
  - Discussion invite: Requires N₂ responses (configurable)

### Invite Consumption
- **Configurable behavior** (default: consumed when accepted)
- Discussion invites are only consumed when:
  1. The invite is accepted by the invitee, AND
  2. The invitee participates in the discussion for the first time
- Users can decline invitations without consuming the inviter's invite

### Invite Visibility & Social Capital
- All users can view any user's invite metrics:
  - Invites acquired (total earned)
  - Invites used (total spent)
  - Invites banked (current balance)
- Formula: `acquired = used + banked` (under normal circumstances)
- If `acquired > (used + banked)`: Indicates user has been penalized through moderation

### Moderation Impact
- Banked invites can be reduced as consequence of moderation actions
- Permanent observer status in a topic resets all earned platform invites to 0

---

## 4. PLATFORM CONFIGURATION VARIABLES

These parameters can be adjusted by platform administrators to optimize platform health, vitality, and safety:

| Variable | Description | Type | Default |
|----------|-------------|------|----------|
| `new_user_platform_invites` | Starting platform invites for new users | Integer | TBD |
| `new_user_discussion_invites` | Starting discussion invites for new users | Integer | TBD |
| `responses_to_unlock_invites` | Responses required before new users can use their invite allocation | Integer | 0 |
| `responses_per_platform_invite` | Responses required to earn 1 platform invite | Integer | TBD |
| `responses_per_discussion_invite` | Responses required to earn 1 discussion invite | Integer | TBD |
| `max_discussion_participants` | Maximum participants per discussion (applied to new invites; existing participants grandfathered) | Integer | TBD |
| `n_responses_before_mrp` | Number of responses before MRP calculation begins | Integer | TBD |
| `max_headline_length` | Character limit for discussion headlines | Integer | TBD |
| `max_topic_length` | Character limit for discussion topic details | Integer | TBD |
| `invite_consumption_trigger` | When invites are consumed: 'sent' or 'accepted' | String | 'accepted' |
| `mrp_calculation_scope` | Which response times to include: 'current_round', 'last_X_rounds', or 'all_rounds' | String | 'current_round' |
| `voting_increment_percentage` | Percentage change for MRL/RTM votes | Integer | 10 |
| `vote_based_removal_threshold` | Percentage required for vote-based removal | Integer | 80 |
| `max_discussion_duration_days` | Maximum total discussion duration (0 = unlimited) | Integer | 0 |
| `max_discussion_rounds` | Maximum number of rounds (0 = unlimited) | Integer | 0 |
| `max_discussion_responses` | Maximum total responses (0 = unlimited) | Integer | 0 |
| `round_1_phase_1_timeout_days` | Maximum time for initial responses before MRP (default 30 days) | Integer | 30 |
| `allow_duplicate_discussions` | Whether duplicate discussion topics are allowed | Boolean | True |
| `response_edit_percentage` | Percentage of response that can be edited | Integer | 20 |
| `response_edit_limit` | Number of times a response can be edited | Integer | 2 |
| `rtm_min` | Minimum allowed Response Time Multiplier | Float | TBD |
| `rtm_max` | Maximum allowed Response Time Multiplier | Float | TBD |
| `mrm_min_minutes` | Minimum allowed Min Response Time (minutes) | Integer | TBD |
| `mrm_max_minutes` | Maximum allowed Min Response Time (minutes) | Integer | TBD |
| `mrl_min_chars` | Minimum allowed Max Response Length | Integer | TBD |
| `mrl_max_chars` | Maximum allowed Max Response Length | Integer | TBD |

---

## 5. DISCUSSION MECHANICS

### 5.1 Creating a Discussion

The discussion initiator must configure:

1. **Topic Headline**: Limited by `max_headline_length` (characters)
2. **Topic Details**: Limited by `max_topic_length` (characters)
3. **Max Response Length (MRL)**: Character limit per response (cannot be changed unilaterally after creation)
4. **Response Time Multiplier (RTM)**: Unitless multiplier for calculating MRP (cannot be changed unilaterally after creation)
5. **Min Response Time (MRM)**: Minimum duration in minutes for MRP calculations (cannot be changed unilaterally after creation)
6. **Initial Invites**: Invite other users (must be < `max_discussion_participants`)

Note: MRL, RTM, and MRM can only be changed through inter-round voting, not by the initiator alone.

### 5.2 Discussion Rounds

#### ROUND 1

**Phase 1: Free-form responses (before MRP)**
1. Users can respond in any order (not sequential) until N responses are posted (N = `n_responses_before_mrp`)
2. If initiator invites fewer users than N, then N is automatically adjusted to equal the number of invited users
3. Time between each consecutive response is tracked: t₁, t₂, t₃, ..., tₙ
4. Maximum timeout: If fewer than N users respond, discussion waits until `round_1_phase_1_timeout_days` (default 30 days) is reached, then discussion is archived
5. Each user can respond exactly once per round

**Phase 2: MRP-regulated responses (after N responses)**
4. Maximum Response Period (MRP) is calculated from response times
5. All subsequent responses must occur within the current MRP
6. MRP recalculates after each new response incorporating latest timing
7. Round continues until:
   - All invited participants respond exactly once, OR
   - No remaining invited users respond before MRP expires

**Round End**
- Final MRP value is tracked for use in next round

#### MRP Calculation Algorithm

```
Input: Response times [t₁, t₂, ..., tₙ], MRM (minutes), RTM (unitless)
Scope: Determined by `mrp_calculation_scope` config
  - 'current_round': Use only times from current round
  - 'last_X_rounds': Use times from previous X rounds
  - 'all_rounds': Use times from all rounds

Process:
  1. Collect response times based on scope configuration
  2. For each tᵢ: if tᵢ < MRM, set tᵢ = MRM
  3. Calculate median of adjusted times
  4. MRP = median × RTM

Output: MRP (in minutes for backend; displayed to users as HH:MM:SS)

Note: Backend calculations use Python/Django datetime; minimum MRP is MRM × RTM
```

**Example:**
- n = 3, MRM = 30 minutes, RTM = 2
- Raw times: t₁=10min, t₂=60min, t₃=40min
- Adjusted: [30, 60, 40]
- Median: 40 minutes
- MRP = 40 × 2 = 80 minutes

**Dynamic Recalculation (using all response times from current round):**
- Next response at t₄=20min
- Adjusted times: [30, 60, 40, 30] (all times from this round)
- New median: 35 minutes
- New MRP = 35 × 2 = 70 minutes

Note: Recalculation uses ALL response times from the applicable scope (current round by default), not just the last N times.

---

#### INTER-ROUND VOTING

**Voting Window**: Duration = final MRP from previous round

**Eligible Voters**: Discussion initiator + all active participants from previous round

**Vote Options** (voted on separately):
1. Adjust MRL: [+increment%, no change, -increment%]
2. Adjust RTM: [+increment%, no change, -increment%]

**Vote Resolution**:
- Each parameter change is voted on separately (two independent votes)
- Simple majority of eligible voters (not just those who cast votes)
- Tie votes (50/50): Motion fails, status quo maintained
- No votes cast within window: Status quo maintained
- Increment amount: Configurable via `voting_increment_percentage` (default 10%)

**Additional Actions**:
- Active participants can invite additional users if current count < `max_discussion_participants`
- If near cap: First-come, first-served basis for new participants

---

#### ROUND 2 AND BEYOND

1. Starts with MRP from previous round (or adjusted MRP if voting changed RTM)
2. MRP regulation applies from the first response
3. MRP recalculates after each response as in Round 1 Phase 2
4. Inter-round voting occurs after each round

**Termination Conditions** (discussion is archived when any condition is met):
- A round receives ≤1 response
- `max_discussion_duration_days` is reached (if configured > 0)
- `max_discussion_rounds` is reached (if configured > 0)
- `max_discussion_responses` is reached (if configured > 0)
- All active participants become permanent observers

---

### 5.3 Observer Status & Reintegration

#### Moving to Observer Status

**Automatic (MRP expiration)**:
- If ANY user responds within MRP, the discussion continues and all users who haven't responded yet still have the opportunity
- If NO user responds within MRP, ALL users who did not respond in that round are moved to observer status and the round ends
- Timing: Users become observers the moment the MRP expires with no response (not when next user responds)

**Manual** (via moderation):
- Through Mutual Removal or Vote-Based Removal mechanisms

#### Returning from Observer Status

**Temporary Observers** - Nuanced reentry rules based on context:

1. **Initial invitees who never participated**: Can join at any point across all rounds (no restrictions)

2. **Moved to observer via mutual removal BEFORE posting in current round**:
   - Can rejoin and post in the same round after 1 full MRP has elapsed from the time of removal
   - Only applies if the round is still active when the MRP period expires
   - If the round has ended, they must wait until 1 MRP has elapsed in the following round

3. **Moved to observer via mutual removal AFTER posting in current round**:
   - Must wait until 1 MRP has elapsed in the following round before they can post
   - Cannot post again in the round where they were removed

4. **Moved to observer due to not posting within MRP (round ended)**:
   - Must wait until 1 MRP has elapsed in the next round before they can post
   - The waiting period begins when the new round starts

**Permanent Observers**:
- Cannot return to active status in that discussion under any circumstances
- Can still read all content
- Cannot send private messages to active participants (if messaging feature is implemented)

---

## 6. MODERATION SYSTEM

### 6.1 Mutual Removal (Kamikaze Lite)

**Process**:
1. User A initiates removal of User B
2. Both User A and User B immediately move to observer status
3. Discussion continues immediately (no pause) if another user responds within MRP from the previous post; otherwise round ends if no remaining users respond within MRP
4. Observer reentry: Follows the nuanced rules in Section 5.3 based on whether the removed user had already posted in the current round
5. After the applicable waiting period: Both can return to active status

**Escalation Rules**:

**User B removed multiple times**:
- 1st removal (by User A): Both to observer, both can return
- 2nd removal (by User C): Both to observer, both can return
- 3rd removal (by User D): Both to observer, **only User D can return**; User B becomes permanent observer

**User initiates multiple removals**:
- If User B removes User A, User C, and User D (3 different users)
- User B becomes permanent observer

**Restrictions** (per discussion, persists across all rounds):
- User A cannot initiate removal of User B again after first time in that discussion
- Other users can still initiate removal of User B
- Removal counts are tracked per discussion (not platform-wide)

---

### 6.2 Vote-Based Removal

**Timing**: After each round ends

**Voting Window**: Duration = ending MRP of that round

**Eligible Voters**: Active participants from that round

**Voting Mechanism**:
- Hidden ballot system
- UI: Grid/gallery view of all active users
- Each voter can select multiple users for removal (including all users if desired)
- Any user who receives votes from super-majority of other active users is removed

**Threshold**: Configurable via `vote_based_removal_threshold` (default 80% of active participants)

**Outcome**: 
- Target user(s) become permanent observer in that discussion
- If discussion initiator is voted out:
  - If initiator previously delegated approval authority: Delegate retains authority
  - If no delegation: No one can approve new uninvited participants

---

### 6.3 Permanent Observer Consequences

**In-Discussion**:
- Can read all content
- Cannot submit responses ever again in that topic
- Cannot regain active status

**Platform-Wide**:
- All earned platform invites reset to 0
- Can still participate in other discussions

---

## 7. RESPONSE EDITING

### Edit Permissions
- Responses can only be edited during the round in which they were posted
- After the round ends, all responses are locked permanently
- No edit history is tracked (only final version at round end is preserved)

### Edit Limitations
- **Maximum editable portion**: Configurable via `response_edit_percentage` (default 20%)
- **Edit attempts**: Configurable via `response_edit_limit` (default 2 edits)
- Implementation: Users can modify up to 20% of their response character count, up to 2 times total

---

## 8. NOTIFICATIONS

### Notification System
- All notifications are user-configurable
- **Critical notifications** (opt-out, default ON):
  - MRP expiring soon (configurable warning threshold, e.g., 25% of MRP remaining)
  - Moved to observer status
  - Inter-round voting window closing soon
  - Discussion will archive (single response warning when ≤1 response in round)
  - Permanent observer consequences warning (before vote-based removal finalizes)
- **Optional notifications** (opt-in, default OFF):
  - Your turn to respond (gentle reminder)
  - Inter-round voting window opened
  - Discussion archived
  - New discussion invite received
  - New response posted in followed discussions
- Delivery methods: In-app (always shown), email, push notifications (user preference)
- In-app notifications cannot be disabled for critical events

---

## 9. USER EXPERIENCE REQUIREMENTS

### 9.1 Discussion Creation Interface

**Problem**: MRL, RTM, and MRM are abstract parameters that are meaningless to most users.

**Requirements**:
1. **Preset Templates**: Offer predefined discussion styles:
   - "Quick Exchange" (low MRM, low RTM, short MRL)
   - "Thoughtful Discussion" (medium values, balanced)
   - "Deep Dive" (high MRM, high RTM, long MRL)
   - "Custom" (reveals raw parameter controls)

2. **Live Preview**: When adjusting parameters (or selecting preset), show plain-language translation:
   - "With these settings, if people respond every 30 minutes on average, each person will have about 60 minutes to respond."
   - Update preview in real-time as user adjusts values

3. **Parameter Validation**: Enforce platform-configured min/max bounds with helpful error messages

4. **Guided Workflow**: Step-by-step creation wizard:
   - Step 1: Topic (headline + details)
   - Step 2: Pace & Style (preset selection or custom parameters)
   - Step 3: Invite Participants
   - Step 4: Review & Launch (show all settings in plain language)

---

### 9.2 MRP Timer Display & Communication

**Problem**: MRP recalculates after every response, creating a "disappearing deadline" that disorients users.

**Requirements**:
1. **Persistent Timer Display**: Always visible when user is in an active discussion:
   - Show current MRP countdown prominently
   - Display as HH:MM:SS for clarity
   - Color-code urgency (green > 50% remaining, yellow 25-50%, red < 25%)

2. **Recalculation Transparency**: When MRP recalculates:
   - Show brief notification: "New response posted. Time remaining updated: 1:23:45"
   - Display what triggered the change ("Sarah's response")
   - Show previous vs. new deadline for context

3. **Guaranteed Minimum Warning**: When user starts typing a response:
   - Lock in a "minimum guaranteed time" based on current MRP
   - Display: "You have at least XX:XX remaining, though this may extend if others post slowly"
   - This prevents the "shrinking deadline" panic scenario

4. **Response Time Context**: Show recent response time patterns:
   - "Last 3 responses averaged 45 minutes"
   - Helps users understand the rhythm of the discussion

---

### 9.3 Voting Interface Clarity

**Problem**: Abstention counts as "no" but this is never stated. Users don't understand vote resolution.

**Requirements**:
1. **Explicit Vote Counting Display**:
   - "X of Y eligible voters must agree for this to pass"
   - Show real-time tally: "Currently: 3 yes, 1 no, 6 not yet voted"
   - Calculate and display: "Need 6 total 'yes' votes to pass (simple majority of 10 eligible voters)"

2. **Abstention Warning**: Clear messaging:
   - "Not voting counts as a 'no' vote"
   - Show this on every voting screen

3. **Voting Window Countdown**: Persistent timer showing time remaining to vote

4. **Vote Result Explanation**: After voting window closes:
   - "Motion to increase MRL by 10% PASSED (6 yes, 2 no, 2 abstained)"
   - "Motion to increase RTM by 10% FAILED (4 yes, 3 no, 3 abstained - needed 6 yes votes)"

---

### 9.4 Moderation Safeguards

**Problem**: Mutual removal and vote-based removal have severe consequences but lack confirmation steps.

**Requirements**:

**Mutual Removal Initiation**:
1. **Confirmation Dialog** before initiating removal:
   - "Are you sure you want to remove [Username]?"
   - "⚠️ You will also become an observer temporarily"
   - "You have initiated [X] of 3 allowed removals in this discussion"
   - "After 3 removals, you will become a permanent observer"
   - Show consequences clearly: "Both you and [Username] will need to wait 1 MRP period before rejoining"
   - Require explicit "Yes, Remove" button (not just "OK")

2. **Escalation Visibility**: Show user's current removal count in discussion:
   - Badge or indicator showing "X/3 removals used"
   - Warning when approaching limit

**Vote-Based Removal**:
1. **Pre-Vote Warning**: Before opening removal ballot:
   - "Vote-based removal is permanent. [Username] will:"
   - "• Never be able to respond in this discussion again"
   - "• Lose all earned platform invites (reset to 0)"
   - "• Be visible to all users as having been removed"

2. **Consequence Display**: During voting:
   - Show impact summary for each potential target
   - Require confirmation before casting removal vote

3. **Post-Vote Notification**: To removed users:
   - Explain what happened and why
   - Show the vote count ("8 of 10 participants voted for removal")
   - Explain consequences and what they can still do (observe, participate in other discussions)

---

### 9.5 Response Editing Interface

**Problem**: The 20% edit rule is difficult to communicate and enforce in a user-friendly way.

**Requirements**:
1. **Character Budget Display**: When editing a response:
   - "You can change up to [X] more characters ([Y]% of your response)"
   - Real-time counter showing remaining edit budget
   - Highlight or indicate which portions have been changed

2. **Edit Attempts Counter**:
   - "Edit [X] of 2" shown clearly
   - Warning when using final edit: "This is your last edit for this response"

3. **Round Lock Warning**: When round is about to end:
   - "This round will end soon. All responses will be locked permanently."
   - Show countdown to round end (or next expected round end)

**Orphaned Draft Protection**:
1. **Graceful Failure**: If user submits after MRP expires:
   - Never discard the user's text
   - Show modal: "The response window has closed. What would you like to do with your response?"
   - Options:
     - "Save as draft for when you can rejoin" (if they're eligible to return)
     - "Copy to clipboard"
     - "Save as private note"
     - "Discard" (requires explicit confirmation)

2. **Pre-Expiration Warning**: When MRP is about to expire:
   - If user has unsaved text in editor, show urgent warning
   - "[Time] remaining! Submit now or your response may be lost."

---

### 9.6 Discussion Archival Warnings

**Problem**: Discussion can be archived when ≤1 response is posted in a round, but users don't know they're about to end the discussion.

**Requirements**:
1. **Single Response Warning**: When a round has exactly 1 response:
   - Show prominent notification to all active participants:
   - "⚠️ This discussion will be permanently archived if no one else responds before [MRP expires]"
   - "[Username] is currently the only person who has responded this round"

2. **Archive Imminent**: As MRP approaches expiration with ≤1 response:
   - Escalating warnings at 25%, 10%, 5% of MRP remaining
   - "Final warning: This discussion will be archived in [time] unless someone responds"

3. **Post-Archive Explanation**: When discussion is archived:
   - Clear message explaining why (which termination condition was met)
   - Confirmation that content is still viewable
   - Option to create a new discussion on the same topic (if allowed)

---

### 9.7 Quote/Reference System

**Problem**: Without threading, linear discussions become incoherent when users try to address multiple previous points.

**Requirements**:
1. **Text Selection Quoting**:
   - Users can select text from any previous response in the discussion
   - "Quote" button appears on selection
   - Quoted text is inserted into response editor with clear formatting
   - Maintains reference to original author and response number

2. **Quote Display Format**:
   ```
   > [Username] (Response #3):
   > "The original quoted text appears here..."
   
   User's response to the quote...
   ```

3. **Multiple Quotes**: Users can quote multiple responses in a single post:
   - Each quote clearly attributed
   - Visual separation between quotes
   - Collapsed/expandable for long quotes

4. **Quote Navigation**: Clicking a quote scrolls/jumps to the original response for context

---

### 9.8 New User Onboarding & Cold Start Experience

**Problem**: New users arrive, see discussions they can't participate in, and have no clear path forward.

**Requirements**:

**Onboarding Flow**:
1. **Welcome Tutorial**: First-time login shows guided introduction:
   - "How discussions work" (rounds, MRP, voting)
   - "How to earn invites" (participate, complete rounds)
   - "How to get started" (observe, request to join, get invited)

2. **Suggested Discussions**: Show curated list of:
   - "Active discussions you can observe"
   - "Discussions welcoming new participants" (flagged by initiators)
   - "Recently archived discussions to read"

**Request to Join Mechanism**:
1. **Observer Request Button**: When viewing a discussion as an observer:
   - "Request to Join This Discussion" button prominently displayed
   - Opens form to send message to discussion initiator (or delegated approver)
   - User can include brief note: "Why I'd like to participate"

2. **Initiator Notification**: Discussion initiator receives notification:
   - "[Username] has requested to join your discussion: [Topic]"
   - Shows requester's invite metrics (social capital)
   - One-click approve/decline
   - Option to send message with decision

3. **Request Status Visibility**: Requester can see status:
   - "Request pending"
   - "Request approved - you can now participate!"
   - "Request declined"

4. **Initiator Tools**: Discussion page shows:
   - List of pending join requests
   - Number of pending requests badge
   - Quick approve/decline interface

**First Participation Incentive**:
- Clear progress tracking toward earning first invites
- "You've completed [X] of [N] responses needed to earn your first discussion invite"
- Celebrate milestones: "First response submitted!" "First round completed!"

---

### 9.9 Inter-Round Voting & Removal Voting Flow

**Problem**: Parameter voting and removal voting occur in the same window but aren't clearly separated.

**Requirements**:
1. **Sequential Presentation**: Present as two distinct steps:
   - Step 1: "Discussion Parameter Voting" (MRL, RTM adjustments)
   - Step 2: "Moderation Voting" (vote-based removal ballot)
   - Clear transition between steps: "Parameter voting complete. Now: moderation voting (optional)"

2. **Optional Skip**: Users can skip moderation voting:
   - "Skip - I don't want to vote to remove anyone"
   - Still counts as abstention (which is a "no" vote, as explained)

3. **Separate Deadlines Display**: Both use same window duration, but show separately:
   - "Parameter voting closes in: [time]"
   - "Moderation voting closes in: [time]"

4. **Completion Tracking**:
   - "You've completed parameter voting ✓"
   - "Moderation voting: [Not started / In progress / Completed]"

## 10. TIME HANDLING

### Timezone Management
- All time tracking is relative to previous response (not absolute timestamps)
- Response times calculated as duration between consecutive posts
- No timezone conversion needed for MRP calculations
- User-facing time displays should show in user's local timezone for clarity
- Backend stores UTC timestamps but calculates durations for MRP

---

## 11. DISCUSSION ARCHIVAL

### Archive Triggers
- Discussion automatically archives when:
  - Termination conditions met (see Section 5.2)
  - All active participants become permanent observers
  - Round 1 Phase 1 timeout reached

### Archive Behavior
- Archived discussions cannot be restarted
- Duplicate discussions (same topic) are allowed by default (configurable via `allow_duplicate_discussions`)
- All content remains viewable by all platform users
- Responses locked in final state (no further edits)

### Archive Warnings (see Section 9.6 for UX requirements)
- Users must be warned when a discussion is about to archive
- Particularly critical when ≤1 response has been posted in a round

---

## 12. PLATFORM ADMINISTRATION

### Admin Roles
- **Platform Creator**: Original admin with full authority
- **Delegated Admins**: Users granted admin privileges by platform creator
- **Same Authority**: All admins have equivalent permissions

### Admin Capabilities
- Modify all platform configuration variables
- Access analytics and reporting
- Manage user accounts (bans, verification issues)
- Cannot directly moderate individual discussions (handled by participants)

---

## 13. ANTI-ABUSE MEASURES

### Account Protection
- Phone number verification required
- Behavioral analysis for spam detection
- Multi-account detection and prevention
- Automatic bans for spammy patterns

### Discussion Integrity
- Platform cap on participants prevents overwhelming discussions
- MRP prevents speed-based manipulation
- MRM prevents unreasonably fast-paced discussions
- Configurable bounds on RTM, MRM, MRL prevent extreme values

---

## 14. RESOLVED QUESTIONS & IMPLEMENTATION DECISIONS

All 40 original questions have been answered. Key decisions:

1. **User System**: One account per user, phone verification, optional data preservation on deletion
2. **Invites**: Consumed when accepted + first participation; earned per response
3. **Time Units**: MRM in minutes, display as HH:MM:SS, backend uses datetime
4. **Round 1 Phase 1**: 30-day timeout if < N responses
5. **MRP Scope**: Configurable (current round, last X, or all rounds)
6. **Response Order**: Any order, not sequential
7. **Observer Timing**: When MRP expires with no response
8. **Observer Reentry**: Nuanced rules based on when/why user became observer (see Section 5.3)
9. **Voting**: Separate votes for MRL/RTM, ties fail, 10% increment, abstention = no
10. **Removal Scope**: Per discussion, not platform-wide
11. **Vote-Based Removal**: 80% threshold, hidden ballot, multiple targets allowed
12. **Initiator Authority**: Can be voted out; approval authority transferable
13. **Max Participants**: Grandfathers existing participants if cap lowered
14. **Editing**: 20% of response, 2 times, only during posting round (with character budget UI)
15. **Notifications**: Critical notifications opt-out (default ON), optional notifications opt-in (default OFF)
16. **Timezone**: Relative durations, not absolute times
17. **Archival**: Permanent, duplicates allowed, with warnings (see Section 9.6)
18. **Admin Tiers**: Creator + delegated admins (equivalent authority)
19. **Private Messaging**: Future feature consideration - referenced in observer restrictions but not yet specified
20. **UX Requirements**: Comprehensive requirements added (see Section 9) for discussion creation, MRP display, voting clarity, moderation safeguards, editing, archival warnings, quoting, and onboarding

---

## 15. OPEN QUESTIONS & CLARIFICATIONS NEEDED

Remaining items to determine through testing and design:

1. **Default numeric values** for platform configuration variables (marked as TBD in table)
2. **Allowable ranges** for RTM, MRM, and MRL to prevent abuse
3. **UI/UX implementation details**:
   - Vote-based removal grid/gallery interface design
   - Character budget counter for edit tracking
   - Quote/reference system implementation
   - MRP timer display and recalculation notifications
   - Discussion creation preset templates
4. **Performance optimization** for MRP recalculation with large response sets
5. **Edge cases** in multi-user simultaneous removal scenarios
6. **Private messaging system**: Whether to implement, scope, and feature set (currently only mentioned as restriction for observers)
7. **Request-to-join workflow**: Detailed implementation of approval/decline flow and notifications

---

## 16. RECOMMENDED DATABASE MODELS (Django)

### Core Models Needed
1. **User** (extends Django User)
   - Phone number (unique)
   - Invites acquired, used, banked (platform and discussion)
   - Behavioral analysis flags
   - Admin status
   - Account deletion preference

2. **PlatformConfig**
   - All configurable variables from Section 4
   - Versioned for audit trail

3. **Discussion**
   - Topic headline, details
   - Configuration (MRL, RTM, MRM)
   - Status (active, archived)
   - Initiator (FK to User)
   - Delegated approver (FK to User, nullable)
   - Created timestamp
   - Archived timestamp (nullable)

4. **DiscussionParticipant**
   - Discussion (FK)
   - User (FK)
   - Role (initiator, active, temporary_observer, permanent_observer)
   - Joined timestamp
   - Observer since timestamp (nullable)
   - Observer reason (null, mrp_expired, mutual_removal, vote_based_removal)
   - Posted in round when removed (boolean) - for determining reentry rules
   - Removal count (integer) - tracks mutual removals initiated
   - Can invite others (boolean)

5. **Round**
   - Discussion (FK)
   - Round number (integer, indexed)
   - Start timestamp
   - End timestamp (nullable)
   - Final MRP (minutes)
   - Status (in_progress, voting, completed)

6. **Response**
   - Round (FK)
   - User (FK)
   - Content (text)
   - Character count
   - Created timestamp
   - Last edited timestamp (nullable)
   - Edit count (default 0)
   - Characters changed total (for 20% rule tracking)
   - Time since previous response (minutes)
   - Is locked (boolean, true after round ends)

7. **Vote** (Inter-round parameter voting)
   - Round (FK)
   - User (FK)
   - MRL vote (increase, no_change, decrease)
   - RTM vote (increase, no_change, decrease)
   - Timestamp

8. **RemovalVote** (Vote-based moderation)
   - Round (FK)
   - Voter (FK to User)
   - Target (FK to User)
   - Timestamp

9. **ModerationAction**
   - Discussion (FK)
   - Action type (mutual_removal, vote_based_removal)
   - Initiator (FK to User)
   - Target (FK to User)
   - Round occurred (FK to Round)
   - Timestamp
   - Is permanent (boolean)

10. **Invite**
    - Inviter (FK to User)
    - Invitee (FK to User, nullable before acceptance)
    - Invite type (platform, discussion)
    - Discussion (FK, nullable for platform invites)
    - Status (sent, accepted, declined, expired)
    - Sent timestamp
    - Accepted timestamp (nullable)
    - First participation timestamp (nullable)

11. **JoinRequest** (NEW - for observer request-to-join feature)
    - Discussion (FK)
    - Requester (FK to User)
    - Approver (FK to User) - discussion initiator or delegate
    - Status (pending, approved, declined)
    - Request message (text, optional)
    - Response message (text, optional)
    - Created timestamp
    - Resolved timestamp (nullable)

12. **NotificationPreference**
    - User (FK)
    - Notification type (enum)
    - Enabled (boolean) - default True for critical, False for optional
    - Delivery method (email, push, in_app)

13. **ResponseEdit**
    - Response (FK)
    - Edit number (1 or 2)
    - Previous content (text)
    - New content (text)
    - Characters changed (integer)
    - Timestamp

14. **DraftResponse** (NEW - for orphaned draft protection)
    - Discussion (FK)
    - Round (FK)
    - User (FK)
    - Content (text)
    - Created timestamp
    - Saved reason (mrp_expired, user_saved, round_ended)

### Key Relationships
- User ↔ Discussion (Many-to-Many through DiscussionParticipant)
- Discussion → Round (One-to-Many, indexed by round_number)
- Round → Response (One-to-Many)
- Round → Vote (One-to-Many, inter-round parameter voting)
- Round → RemovalVote (One-to-Many, moderation voting)
- Response → User (Many-to-One)
- Response → ResponseEdit (One-to-Many, max 2)
- Discussion → ModerationAction (One-to-Many)
- Discussion → JoinRequest (One-to-Many)
- User → Invite (One-to-Many as inviter)
- User → JoinRequest (One-to-Many as requester)
- User → NotificationPreference (One-to-Many)
- User → ModerationAction (as both initiator and target)
- User → DraftResponse (One-to-Many)

### Critical Indexes
- DiscussionParticipant: (discussion_id, user_id), (user_id, role), (observer_since, observer_reason)
- Round: (discussion_id, round_number), (status)
- Response: (round_id, user_id), (created_timestamp)
- Vote: (round_id, user_id)
- RemovalVote: (round_id, voter_id), (round_id, target_id)
- Invite: (inviter_id, status), (invitee_id, status)
- JoinRequest: (discussion_id, status), (requester_id, status), (approver_id, status)
- DraftResponse: (discussion_id, user_id), (round_id, user_id)

---

## 17. IMPLEMENTATION PRIORITIES

### Phase 1: Foundation & Core User Flow
- Django project setup with PostgreSQL database
- User model extension (phone verification, invite tracking)
- Platform configuration system (PlatformConfig model + admin interface)
- User authentication (phone-based)
- Invite system:
  - Platform invites (send, accept)
  - Discussion invites (send, accept, first participation trigger)
  - Invite tracking (acquired, used, banked)
- **UX: Basic onboarding tutorial** (see Section 9.8)

### Phase 2: Discussion Creation with UX
- **Discussion creation wizard** with preset templates (see Section 9.1):
  - Step-by-step workflow
  - Preset discussion styles (Quick Exchange, Thoughtful Discussion, Deep Dive, Custom)
  - Live preview of parameter implications
  - Plain-language parameter translation
- Discussion participant management
- **Join request system** (see Section 9.8):
  - Observer request-to-join interface
  - Initiator approval workflow
  - Request status notifications

### Phase 3: Round 1 with Enhanced UX
- Round 1 Phase 1: Free-form responses
  - Response submission (character limit validation)
  - Time tracking between responses
  - **Response editing with character budget counter** (see Section 9.5)
  - **Quote/reference system** for coherent linear discussions (see Section 9.7)
- Round 1 Phase 2: MRP-regulated responses
  - MRP calculation algorithm
  - **Enhanced MRP timer display** (see Section 9.2):
    - Persistent countdown with color-coding
    - Recalculation transparency notifications
    - Response time pattern context
  - **Orphaned draft protection** (see Section 9.5)
  - Observer status on missed deadline
  - Round completion logic

### Phase 4: Multi-Round Mechanics with Voting UX
- **Inter-round voting system with clarity** (see Section 9.3 and 9.9):
  - Separate sequential steps for parameter vs. moderation voting
  - Explicit vote counting display
  - Abstention warnings
  - Majority calculation and tie handling
  - Parameter adjustment application
- Round 2+ mechanics
  - MRP inheritance and recalculation
  - Configurable MRP scope
- **Observer reintegration with nuanced rules** (Section 5.3):
  - Different rules based on when/why user became observer
  - Wait period tracking and enforcement
  - Initial invitee join-anytime logic

### Phase 5: Moderation System with Safeguards
- **Mutual removal with confirmation** (see Section 9.4):
  - Confirmation dialog with consequence warnings
  - Escalation tracking (removal count 0/3 display)
  - Bilateral observer status
  - Per-discussion restriction tracking
- **Vote-based removal with warnings** (see Section 9.4):
  - Pre-vote consequence warnings
  - Hidden ballot UI (grid/gallery)
  - Super-majority calculation
  - Post-removal notifications to affected users
  - Multiple-target support
- Permanent observer enforcement
- **Invite penalty system with visibility**:
  - Banked invite reduction
  - Platform invite reset
  - Public visibility of moderation impact

### Phase 6: Discussion Lifecycle & Archival with Warnings
- **Discussion termination with warnings** (see Section 9.6):
  - Single response warning (≤1 response alert)
  - Escalating warnings as MRP approaches with low responses
  - Round 1 Phase 1 timeout (30 days)
  - Max duration/rounds/responses limits
  - All participants permanent observers condition
- Archival system
  - Response locking
  - Post-archive explanation
  - Duplicate discussion detection
  - Archive browsing interface

### Phase 7: Enhanced Notifications & Real-Time
- **Critical notifications (opt-out, default ON)** (see Section 8):
  - MRP expiring soon (25% threshold)
  - Moved to observer status
  - Discussion will archive warning
  - Permanent observer consequences
  - Inter-round voting closing
- **Optional notifications (opt-in, default OFF)**:
  - Gentle reminders
  - New invites
  - Discussion archived
- Delivery methods:
  - In-app (always shown for critical)
  - Email
  - Push notifications
- Real-time features:
  - Live MRP countdown
  - New response indicators
  - Round transition alerts

### Phase 8: Anti-Abuse & Admin Tools
- Phone number verification
- Behavioral analysis system
- Multi-account detection
- Spam pattern recognition
- Admin dashboard:
  - Platform config management
  - User management
  - Analytics and reporting
  - Discussion oversight

### Phase 9: Polish & Optimization
- Performance optimization:
  - MRP calculation caching
  - Database query optimization
  - Response pagination
- UI/UX refinement:
  - Mobile responsive design
  - Accessibility improvements (WCAG compliance)
  - User flows based on testing feedback
- Testing:
  - Unit tests for MRP algorithm
  - Integration tests for round flow and observer reentry
  - Load testing for concurrent discussions
  - User acceptance testing

---

**Document Version**: 3.0  
**Last Updated**: 2026-02-02  
**Status**: Comprehensive specification with UX requirements - Ready for development

**Change Log**:
- v1.0 (2026-02-02): Initial specification with 40 open questions
- v2.0 (2026-02-02): All questions resolved, comprehensive specification complete
- v3.0 (2026-02-02): Major UX enhancements and observer reentry refinements:
  - Replaced simple observer_reentry_rule with nuanced reentry logic based on context
  - Added comprehensive Section 9: User Experience Requirements (9 subsections)
  - Changed critical notifications from opt-in to opt-out (default ON)
  - Added discussion creation presets and live parameter preview requirements
  - Enhanced MRP timer display requirements with recalculation transparency
  - Added confirmation dialogs and consequence warnings for moderation actions
  - Added voting clarity requirements (explicit abstention = no vote messaging)
  - Added orphaned draft protection and character budget counter for editing
  - Added quote/reference system requirements for linear discussion coherence
  - Added request-to-join mechanism for new user cold start experience
  - Added new database models: JoinRequest, DraftResponse
  - Enhanced DiscussionParticipant model with observer context fields
  - Updated implementation priorities to integrate UX requirements throughout
  - Clarified that private messaging is a future consideration, not current feature
  - Added archive warning requirements (particularly for ≤1 response scenarios)
