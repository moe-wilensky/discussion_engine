1. The "Disappearing Deadline" Anxiety

This is the single biggest UX risk in your current spec.

    The Mechanic: MRP recalculates after every response using the median of the current round.

    The Scenario:

        You are in a group of 5.

        You start writing a thoughtful, complex argument. The timer shows 2 hours remaining.

        While you are typing, 3 other users post short, "I agree" responses in quick succession (10 minutes each).

        The MRP creates a new median based on those 3 quick responses.

        The Consequence: Suddenly, your timer jumps from 2 hours down to 20 minutes while you are mid-sentence.

    The UX Friction: This creates "Type Panic." Users will feel punished for writing in-depth responses because the "fast/low-effort" users are effectively shortening the deadline for the "slow/high-effort" users.

    The Fix:

        Lock the Deadline Downward: Once an MRP is set for a round, it can extend if slow people respond, but it should never shrink based on fast people. The deadline displayed to a user when they start typing should be a "guaranteed minimum."

2. The "Sniper" Standoff (Last-Mover Advantage)

In a system where everyone gets exactly one response per round, the person who posts last holds the most power.

    The Mechanic: Everyone can read the thread before posting.

    The Behavior:

        If I post first, 4 other people can pick apart my argument, and I cannot defend myself until Round 2.

        If I post last, I can rebut everyone else's points, and nobody can respond to me until the next round.

    The UX Friction: This incentivizes stalling. Users will "camp" on the discussion, waiting for the timer to tick down so they can be the last to post (the "Sniper"). This leads to a flurry of activity in the final 5 minutes of the MRP, increasing the risk of people accidentally timing out and becoming observers.

    The Fix:

        Blind Rounds (optional): Responses are hidden until the round closes (like a "reveal").

        OR Draft Incentives: Bonus "invites" or "reputation" for posting within the first 50% of the MRP window.

3. The "Orphaned Draft" Rage-Quit

    The Mechanic: "Users become observers the moment the MRP expires... [and] cannot submit responses ever again in that topic".

    The Scenario:

        A user spends 20 minutes typing a response on their phone.

        They get distracted or the "Disappearing Deadline" (see point #1) hits them.

        They hit "Submit" 1 second after the MRP expires.

    The UX Friction: If the system simply rejects the request and reloads the page as an "Observer," the user loses their text. This is a "rage-quit" moment.

    The Fix:

        Graceful Failure: If a user submits after the buzzer, the system must save their text and offer to:

            "Post as a private note for yourself."

            "Save to clipboard."

            "Queue as a draft for the next round" (if they are eligible to re-enter).

4. The "Wall of Context" Problem

    The Mechanic: Users respond in any order.

    The Scenario:

        Round 1 has 10 participants.

        Participant A asks a question about "Topic X."

        Participants B, C, and D ignore A and talk about "Topic Y."

        Participant E wants to answer A, but their post appears 5th in the list.

    The UX Friction: Without threading (replying to a specific post), the linear feed becomes a disjointed "stream of consciousness." In a standard forum, you can reply multiple times to clarify. Here, you have one shot. If you have to address User A's point and User B's point and User C's point in a single block of text, your response becomes a messy "mega-post."

    The Fix:

        Quote/Reference UI: Even if the display is linear, the input UI needs a robust "Select text to quote" feature so users can clearly visually signal who they are responding to within their single allotted post.

Summary of UX Recommendations

    Stabilize the Timer: The MRP should never shrink during an active round; it should only extend or stay static.

    Incentivize Early Posting: Gamify "being first" to prevent everyone from waiting until the last minute.

    Draft Safety: Never discard user input, even if they miss the deadline.

    Quoting Tools: Essential for keeping a linear, single-response conversation coherent.