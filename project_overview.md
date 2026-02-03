# PROJECT SUMMARY

 **The discussion engine is an attemp to create a tool to foster discussion and collaboration online amungst diverse individuals**

**key principals**

- no disucussions are private but who can activly contirbute is based both on group and individaul actions 
- All discussion is iterativly performed with all directly invovled users providing input
- the space and time users have to respond varies dynamiaclly and can be set directly by users or adjsuted automatically based on user behaviour
- any required moderation shoudl be perfomred by the users themssleves and be done in such a way as to foster reentry into the conversation of those uses whos actions were constrined

**the User**

- all platform users must be invited by another user
- any user can start a discussion topic
- any user may observe any discussion
- users can only join in the active discussion of a topic after being invited either by user who started the topic or by another user activly engsaging in the topic

**invites**

- users can accumualte invites by completing full rounds of discussion
- there are two types of invites: platform invites and discussion invites
- platfrom inviates are more limted than disccion invites
- inviates aquired, used and banked by an individual user will be visibel to all users and serve as a sort of social capital 
- banked invites can be reduced as a consequnce of moderation actions against a user, with useres whose invites aquired > bank + used implies repreimand


**Key Platfrom Variables**

these are paramteres that the platmofm creater can adjsut and optimaized to inflcunce the over health, vitatily and saftey of the platfom

- new User startign number of platfrom invites
- new User startign number of discussion invites
- number of responces required to achieve a platfom invite
- number of responces required to achieve a disucssion invite
- maximum number of conversation participants
- number (n) of responces required before the discussion response time is set in first round of discussion

# DISCUSSION MECHNAICS

## Creating a discussion

1) user creates a discussion topic headline limited in character length by teh key plafrom variable "max headline length"
2) user details the discussion topic limited in character length by teh key plafrom variable "max Topic length"
3) user sets max response length (MRL)
4) user sets response time multiplier (RTM)
5) user sets the min response time (MRM) for use in claculating maximum response period
5) user invites other users to discuss the topic (this number must be less than the "max discussion participants" set in step 5)

NOTE: After initation the discussion, the initating user will repsond jsut as other discussion particiapnts, thier only addionial autority is to allow uninvited users to join the discussion

## The discussion

ROUND 1

1) any user can respond at any time (ie in seconds, hours, or days), the time between the intital invites and teh frist response is tracked as t1
2) the next user can respond at any time after the first response is posted, the time between the teh frist and second response is tracked as t2
3) users can continue to respond with no time limt between thier response and the previous (though this time will continue to be tracked fro each response) untill the number of responces reaches Key Platfrom Variables n
4) when the number of responces reach n the times between resposnces will be used to calcuale a maximum response period (MRP)
5) after the maximum response period has been calculated, the next response must occour wihtin this period
6) with each subsiquent reponse that does occour within the maximum respoonse period, the MRP is recalulated to incorpate hte duratio between the last two prompts
7) the disccussion continues until all invited participants have responded exactly once or none of the remaining invited users respondes before the MRP expires at this point the first round of disucssion is complete 
8) at the end fo the first round, the round end MRP it tracked for use in the next round

INTERROUND VOTING

For a period that is the length of the MRP at the end of the previous round all round 1 responderd and teh discussion initiatior  have a chance to vote on the follwoing:

1) increase or reduce the MRL
2) increase or decrease the RTM

possible changes to MRL or RTM will be a single fixed increment (eg +10%, no chnage, -10%)

votes to be decided on simple amjority or all eleigbale voters (ie those that actvily participated in the previous round) not jsut hsoe that actully vote 

Active participants can also invite additoinal particpants if the current number of particpants is less than the platform cap, noew particpants are allowed to join in a first come first served apprach is the currnet number of partipants is clsoe to the platform cap. 


ROUND 2 

1) The MRP (or adjsuted MRP if voting lead to that between rounds) is in place formm the start of the second round.
2) the MRP is adjsuted after each response and the round proceeds jsut as round 1 did after teh MRP was set in round 1

interround voting and subsequnt rounds continue until a round where only 1 or no usrs respond. 

how the MRP is Calcualted

intial repsonse time and resposonse times up to response n: t1, t2, t3, ..., tn

if any of these reponse times are less than the MRM, that response time is adjsuted up to the MRM value

the median of these response times is multiplied by the RTM to calcualte teh MRP

eg if n = 3, MRM = 30 minutes and RTM = 2 

t1 = 10 minutes
t2 = 60 minutes
t3 = 40 minutes

then t1 is set to 30 minutes and the median of 30, 60, and 40 = 40 minutes, so 40 minuntes x the RTM of 2 = 80 minutes = MRP

during a round this avle is re claaulted after each response. so if the next response happens 20 mintes later (ie t4=20) t4 is adjsuted to 30 and the new MRP is set to 70

if a user who had previously be active in a disucssion, but ends the round by not reponding within the MRP, this user is moved to observer status, they can rejoin the discussion either in the next round or after the a period euqwal to the MRP (tbd) at hte point where they were moved to observer status. 

NOTEs

- any intital invitee can join the discussion for the first time at any point across all rounds
- any paltform user can join a discussion as an opserver, but must request acess from the user whol intiated the discussion topic before becoming active aprticpants

Moderation System
Mutual Removal (Kamikaze Lite)
How it works:

User A initiates removal of User B
Both users A and B immediately moved to observer status for 1 MRP or 1 round (tbd)
after 1 MRP both users can retrun to active in the same way just as if they had been moved to observer for not rposting wihtin the MRP
user A can not initate removal of user B again, how ever user be can be moved to observer status by a differnt active user (eg user C), though again, this casues user C and user B to move to observer status. if user B if moved to observer status a third theim (eg bu user D) both user D and B move to observerstaus, but only user D may return to active, user B's observerstatus has eesentially become perminant

if a user moves three differnt other users to observer status, (eg B moves A, then B moves C, then B moves D) B will become a perminant observer

Vote-Based Removal
How it works:

After each round, users can vote to remove a specific user
Voting window: Must vote within the ending MRP
Threshold: super Majority of active users must vote in favor
Outcome: Target gets moved to Permanent observer 


Permanent observer:

Can still read all content
Cannot submit responses ever again (in that topic)
All earned platform invites reset to 0
