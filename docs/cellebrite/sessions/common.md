# Phone sessions: shared material for every round

Moderated sessions on the phone screens, run by a person (07 section 10.3). Each round's pack is this file plus the round's task cards (`R0.md` to `R3.md`). Rounds R0 and the practice parts of later rounds use the training case only; R1 to R3 use real phones read by the participant, and nothing from them is written down except counts and the participant's words about the interface.

## 1. Before the session

- Up to 5 participants per round, about 60 minutes each, in their own browser at `http://104.196.62.215:5174`, signed in as themselves.
- Tasks rotate between rounds; one new person joins per round where the team allows. Note for each participant which rounds they have already done (learning effect).
- The coordinator sets the release hold for the session window, so Loupe does not change during a session.
- The moderator has: this file, the round's task cards printed or on a second screen, one result sheet per participant, and a timer.
- No screen video and no screenshots are taken. Notes never hold case content: no names, numbers, message text, places or evidence numbers, even from the training case.

## 2. Consent wording (read aloud, then ask for a yes)

> Thank you for helping. We are testing Loupe's phone screens, not you. There are no wrong answers: if something is hard, that is what we need to find out.
>
> I will give you some tasks and ask you to think aloud as you work. I will time each task and count clicks and mistakes, and at the end ask you to fill in a short questionnaire.
>
> I will not record your screen or your voice and I will not take screenshots. My notes hold times, counts, and what you say about the screens. They never hold anything from the case: no names, numbers or messages.
>
> Your name will not appear in the results; you will be "Participant 1", "Participant 2" and so on. You can stop at any time, skip any task, or ask for your notes to be deleted afterwards.
>
> Are you happy to go ahead?

Record the answer on the result sheet. Without a clear yes, do not run the session.

## 3. The case story (training case)

Read this aloud at the start of R0, and of any practice task in later rounds. Everything in the training case is invented.

> Two phones were seized on 3 and 10 May 2024 in an enquiry into payments to a storage business. Phone C5 belongs to Emrys Juniper, phone C6 to Corin Ashdown. Both phones were in Eastern time. The two owners message each other often, and several of the people on their phones also appear on Emrys Juniper's bank statement, which is in the case.
>
> The team wants to know: who these two talk to most, whether their messages line up with the payments, and what the system has read from the phones that a person still needs to check.

Use only this story for relevance questions ("which of these matters most?"); the participant should not need to know anything else.

## 4. Running each task

1. Read the task card aloud exactly as written. Do not add hints or name controls.
2. Start the timer when you finish reading. Stop it when the participant says they are done or gives up, or at the card's time limit.
3. Record: success (yes, partly, no), human time in seconds (subtract time spent waiting for Loupe, noted separately), actions (clicks and key presses), errors (a wrong path the participant had to back out of), and the single-ease rating.
4. Single-ease question, after each task: "Overall, how easy or hard was that task? 1 is very hard, 7 is very easy."
5. If the participant asks for help, answer "What would you try?" once. If still stuck, mark the task "no" and move on.

## 5. Comprehension probes (every round)

Ask each probe while the participant is looking at the relevant screen. Score each correct or incorrect against the answer key. Do not correct a wrong answer during the session.

| # | Probe | Correct when the participant |
|---|---|---|
| P1 | "What time and day was this sent, in which zone?" (point at a message) | gives the day, the time and the zone shown, e.g. Eastern time, and does not convert it to their own zone without saying so |
| P2 | "Was the phone in use here?" (point at a **No data** band) | says the phone holds no records for that period and that this does not show it was unused |
| P3 | "Is this person confirmed as the sender?" (point at a row with **Mapped by the system, not yet confirmed**) | says no: the system read it and no person has checked it yet |
| P4 | "Are all messages between these two on this edge?" (point at a count or an edge between two people) | says the count covers what the scope shows and names what could be outside it (other numbers, other phones, readings not confirmed) |

Any incorrect answer on time, absence or provenance (P1 to P3) is a top-priority follow-up: the moderator sends it to the coordinator the same day, worded as a counts-only finding ("P2 incorrect for 2 of 4 participants on the Phone summary coverage bands").

## 6. Result sheet (one per participant)

```
Round: R_   Date:            Moderator:            Participant: P_
Rounds already done by this participant: ____
Consent given: yes / no

Task | Success (yes/partly/no) | Human time (s) | Waiting (s) | Actions | Errors | Ease (1-7) | Words about the screen
-----+-------------------------+----------------+-------------+---------+--------+------------+-----------------------
T1   |                         |                |             |         |        |            |
T2   |                         |                |             |         |        |            |
...  |                         |                |             |         |        |            |

Probes: P1 correct / incorrect   P2 correct / incorrect   P3 correct / incorrect   P4 correct / incorrect

System Usability Scale (1 strongly disagree to 5 strongly agree):
 1 I think that I would like to use these phone screens frequently.          __
 2 I found them unnecessarily complex.                                        __
 3 I thought they were easy to use.                                           __
 4 I think I would need help from a technical person to use them.            __
 5 I found the various functions well integrated.                             __
 6 I thought there was too much inconsistency.                                __
 7 I would imagine most people would learn to use them very quickly.          __
 8 I found them very cumbersome to use.                                       __
 9 I felt very confident using them.                                          __
10 I needed to learn a lot of things before I could get going with them.      __
SUS score (0-100): ____

Anything else the participant said about the screens (their words, no case content):
```

SUS score: for odd items subtract 1 from the answer; for even items subtract the answer from 5; add the ten results and multiply by 2.5.

## 7. Analysis method

1. **Per task:** success rate (yes counts 1, partly 0.5), median human time, median actions, error count, median ease. Compare against the task card's target and against the reference levels: 4 of 5 succeed, median ease 5.5 or more, SUS 75 or more. These are reference levels, not pass marks.
2. **Probes:** correct count per probe out of participants asked.
3. **Problems:** list each distinct problem once, with how many participants hit it, the task, and the screen. Rank by: misreading of time, absence or provenance first; then task failure; then slowness; then preference.
4. **Learning effects:** report results separately for participants new to this round's tasks and returning participants.
5. **Labelling:** with fewer than about 20 participants every result is **directional**. No result passes or fails a job.
6. **Hand-off:** every problem becomes one concrete item with its own scripted regression test, sent with `tell.sh` to the job that owns the screen (or to `followups` once that job is finished). Decisions in 07's decisions table that a round was set to test (the "what reverses it" column) are marked kept or reversed, with the counts that decided it.
7. **What is sent:** counts, times, probe scores and the participants' words about the interface. Never case content and never a participant's name.
