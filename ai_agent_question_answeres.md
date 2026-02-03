## 7. OPEN QUESTIONS & CLARIFICATIONS NEEDED

### User System
**Q1**: Can a user be invited to the platform multiple times, or is one invite sufficient for permanent membership?
- **Reference**: Lines 13-14 (user invitation system)

Answer: users can only join the platfrom once and ideally  systems will be put inplace to avoid users creating mulitple accounts, Phone number + behavioral analysis (spammy patterns = ban) - Standard industry practice

**Q2**: Do new users receive invites immediately upon joining, or after some initial action? t
- **Reference**: Lines 52-53 (new user starting invites)

Asnwer: here wil lbe a configurable numeb of responses required to unlaock the new accoun tinvites allotment, possibly 0 (ie invites are imeediatly avilble to to any number of responces required

**Q3**: What happens to unused discussion/platform invites when a user becomes inactive?
- **Reference**: Lines 41-44 (invite banking)

answer: nothing, if a user deletes thier account they can coose to delete all daat or keep them asosated with thier id if they want to rejoin in the future

### Invite Mechanics
**Q4**: Are invites consumed when sent, or only when accepted?
- **Reference**: Lines 41-49 (invite system)

answer: configurable, but starting with when accepted

**Q5**: Can users decline discussion invitations, and if so, what happens to the invite?
- **Reference**: Lines 26-27 (invitation mechanics)

answer: discussion invites are only used when accepted and the invited user participates in teh discussion they were invited to for the first time

**Q6**: How exactly are invites "earned" - per response, or per completed round?
- **Reference**: Lines 43-44 vs 54-55 (conflicting information: "completing full rounds" vs "number of responses required")

answer: configurable, becasue 1 round equal 1 response, the configuration woudl be 1 number

### Discussion Configuration
**Q7**: Are MRL, RTM, and MRM measured in the same time units, or can they differ?
- **Reference**: Lines 66-68 (discussion creation parameters)

max response length (MRL): characters
response time multiplier (RTM): unitless, its jsut a mulitplier
min response time (MRM): minutes

(note please ensure you undersand how these vlaeus are used, it should ahve been clear that these coudl not have the same units)

**Q8**: What are reasonable min/max bounds for RTM, MRM, and MRL to prevent abuse?
- **Reference**: Lines 66-68 (no constraints specified)

configurable, allowbale ranged to be ddetermeind though teseting

**Q9**: Can the discussion initiator change these parameters after creation, or only through voting?
- **Reference**: Lines 66-68 vs 103-110 (unclear authority)

only by votgin, the intiatiors only addtional athority over other users after startin a disucsusison is to allow uninvited users to join if they ask to join, this athority can be delgated to another active participant

### MRP Calculation
**Q10**: What time unit is used for response tracking (seconds, minutes, hours)?
- **Reference**: Lines 79, 127-147 (no explicit unit definition)

answer: do be dispalyed to suer in app as HH:MM:SS backend calualtions shoudl ue what ever makes sen for programmgin envonment (wsl/python/django)

**Q11**: During Round 1 Phase 1, is there ANY time limit, or can users take days/weeks/months?
- **Reference**: Lines 75-77 (says "at any time" but unclear if there's an upper bound)

answer: configureable, 1 month limit intially

**Q12**: If fewer than N users respond in Round 1, how is MRP calculated?
- **Reference**: Lines 78-81 (assumes N responses always reached)

answer: if intiator invites fewer users than N, the number fo invited users becomes N, if the user invites more than N but fewr then N respond, the discussion sits untill the max time threshold is hit (Q11 above)

**Q13**: When recalculating MRP, do we use the last N response times, or all response times from the round?
- **Reference**: Lines 84-85 (unclear which times are included in recalculation)

anser: all response times from a round are used to calculate MRP, configruable between jsut response time in teh current round, the previous X rounds or all rounds

### Round Mechanics
**Q14**: In Round 1, must users respond in a specific order, or can any invited user respond at any time?
- **Reference**: Lines 75-87 (mentions "next user" but unclear if sequential)

answer: absolutly not, only requiremtn is one response per user per round

**Q15**: Can a user respond multiple times in one round, or exactly once per round?
- **Reference**: Line 87 ("all invited participants have responded exactly once")

answer: one response per user per round

**Q16**: If a user misses Round 1 entirely, can they join in Round 2?
- **Reference**: Lines 151-152 vs 87-89 (potential conflict)

answer: yes if a user was active, but then were one of the users in teh next round that was moved to observer (and ending the previous round) they can rejoin after waiting the duration of the MRP they missed

### Voting System
**Q17**: For simple majority voting, how are ties resolved (50/50 split)?
- **Reference**: Lines 107-108 (majority of eligible voters)

answer, motion fails

**Q18**: What is the exact increment/decrement value for MRL and RTM adjustments?
- **Reference**: Line 111 (says "single fixed increment" but not specified)

answer configurable, start iwth 10%

**Q19**: Are multiple parameter changes voted on separately or as a package?
- **Reference**: Lines 103-108 (can vote on MRL and RTM)

answer: separetly two fileds will be shown in app between rounds users make 1 choice in each

**Q20**: If voting window (1 MRP) passes with no votes, what happens - status quo or default change?
- **Reference**: Lines 103-108 (doesn't specify no-vote scenario)

answer: nothgin happens, previous values stand

### Observer Status
**Q21**: When a user fails to respond within MRP, at what exact moment do they become an observer - when MRP expires or when the next user responds?
- **Reference**: Lines 157-158 (timing unclear)

ansawer, agian please confimr you understnad teh dynamics, if nay user responds withgin the MRP the discuccion continues and any users who have not responded yest will still ahve the chance to do so, if noone responds wihtin the MRP all usrers who did in not respond are moved to observer and the round ends 

**Q22**: "1 MRP or 1 round (TBD)" - which rule should be implemented?
- **Reference**: Lines 158, 171 (multiple TBD instances)

answer configurable, all useres who casued the previous roudn to end must eith sit out the next round or wait for 1 full MRP in the next round to respond

**Q23**: Can observers send private messages to active participants or only passively view?
- **Reference**: Lines 157-161 (only specifies can't respond)

answer only passivly view

### Moderation - Mutual Removal
**Q24**: When both users move to observer status, does the discussion continue immediately or pause?
- **Reference**: Lines 168-171 (no specification of discussion flow impact)

answer discussion continues imeediatly if another user respondes wihtin the mrp from teh previus post otherwise if there are no more users to repson or noone else repsonds withgin teh mrp the round ends

**Q25**: If User A removes User B in Round 3, and both return in Round 5, does the "can't remove again" restriction persist across all future rounds?
- **Reference**: Lines 180-181 (unclear temporal scope)

answer, yes, persusts across all rounds, 

**Q26**: Does "3 removals" count across all discussions or per-discussion?
- **Reference**: Lines 175-177, 182-183 (scope unclear)

answer: per discussion

### Moderation - Vote-Based
**Q27**: What is the exact threshold for "super-majority" (66%? 75%? 80%)?
- **Reference**: Line 192 (super-majority not defined)

answer: configurable, start with 80%

**Q28**: Can users vote to remove multiple people in one voting window?
- **Reference**: Lines 188-193 (single or multiple targets unclear)

Answer: yes, after each round every active user can be slected by any other for removel (hidden ballot) if any users get slected by the super majority of other users they are removes 9im envision a grid of all usrs that you can alect liek a gallery, you coudl electe everyone if you wanted to)

**Q29**: Can the discussion initiator be voted out, and if so, who manages new participant approvals?
- **Reference**: Lines 188-193 + 29-30 (initiator authority)

yes, discsusion leader cna be vloted out, they can dleagte another user prior or not, if not, now onw cna join without an invite 

### Platform Variables
**Q30**: Should there be a minimum MRP duration to prevent discussion from moving too fast?
- **Reference**: Lines 52-59 (no minimum MRP configuration variable)

answer:this is taken care of by the min response time (MRM), if all users respond in less tim than this, the MRM x response time multiplier (RTM) becomes the min MRP

**Q31**: What happens if `max_discussion_participants` is changed mid-discussion?
- **Reference**: Line 57 (global setting impact on active discussions)

answer:  if the new max_discussion_participants is fewer than the discussion current number of participants, no new partipants cna be added (but none are automatically removed) new particpants cna be added if the numerb fo particpants drops below the new max_discussion_participants by sttrition

**Q32**: Are there different user tiers/roles at the platform level (admin, moderator, user)?
- **Reference**: Lines 51-59 (only mentions "platform creator")

answer: only admin (plafrom creater and anyone else they choose) all with seom athority

### Data Model Questions
**Q33**: Are discussion rounds numbered/indexed (Round 1, 2, 3...) in the database?
- **Reference**: Lines 73-125 (rounds referenced but not explicitly numbered)

answer: yes Round 1, 2, 3...

**Q34**: How is discussion "completion" or "archival" handled - do discussions ever close permanently?
- **Reference**: Lines 124-125 (only specifies when they stop, not closure)

answer discussion are archived and cna not be restarted. new duplicate discussion are allowed though this is configurable. 

**Q35**: Should the system track edit history if users want to modify their responses?
- **Reference**: No mention of editing responses at all

answer: only the responses that exisit when teh discussion ends shodul be tracked. note that useras are allwoed to edit soem configurabel portion of thier repsonses (starting at 20%) up to 2 times before they are locked. 

**Q36**: Are responses immutable once posted, or can users edit within a time window?
- **Reference**: No specification of edit capability

posts can only be edited durign the roudmn they are made in

### Technical Implementation
**Q37**: Should the system send notifications (email, push) when MRP is expiring, or rely on users to check?
- **Reference**: Lines 82-87 (time limits enforced but no mention of notifications)

plan for user configurabel notifcations, all off by defualt

**Q38**: How should timezone differences be handled for global users?
- **Reference**: Lines 79-87 (time tracking with no timezone mention)

asnwer timezone shodul not matter, only time reltive to previous post

**Q39**: What happens to discussions if all active participants become permanent observers?
- **Reference**: Lines 194-200 (no discussion termination rule for this case)

answer: not sure how this woudl happen unless somone made themselves  aperminant observer, but in any case the disucssion woudl be over

**Q40**: Should there be a maximum discussion duration (e.g., 90 days) to prevent indefinite discussions?
- **Reference**: No mention of upper time bounds

answer configurable, both by round, total responsces, and total duration, start with no limts. 

