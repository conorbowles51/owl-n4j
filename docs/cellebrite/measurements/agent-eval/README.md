# Agent evaluation set (07 section 7.1)

36 questions with known answers on synthetic phones (two phones in one case, a third phone in another case),
written by hand in `backend/tests/test_agent_phone_evaluation.py` and measured through the agent's own tools, as the
model calls them, with the run's case.

## Tool layer, 2026-11-03 (`tool-layer-2026-11-03.jsonl`)

| Setting | Questions | Known total stated | Exactly the known records cited | Refused with the boundary, no records |
|---|---|---|---|---|
| All data | 36 | 36 | 36 | not applicable |
| Significant | 36 | not applicable | not applicable | 36 |

The set covers people by name and by number, both phones and one phone, kinds, windows (one day, a range, open at
either end), word search including no match, between and involving, group chats, paging in order, a copy found twice
counted once, a reading not yet confirmed, a contact summary, one record in full, the phones list, and a phone,
person, number and record that exist only in another case ("Not in this case").

Involving a person counts the group messages that person is party to, as Conversations does; "include group chats"
changes only Between. The phone_messages tool description says so.

## Model answers on live, 2026-11-03 (`model-live-2026-11-03.json`)

The live agent (DeepSeek V4 Pro, as routed in Settings) was asked, signed in over plain http on release ca28a9ef,
"Using the phone tools, how many direct messages and calls are there between A and B? State the total and cite every
record with its rec:// link." for 6 pairs of app identities in the two synthetic cases (2 in the training case, 4 in
the phones-only case), each pair asked two or three times. The known answer is the pair's count on the Graph, which
equals Conversations Between A and B. Each answer's citations are counted from the stored answer text (distinct
rec:// ids).

| Complete answers | Known total stated | Records cited equal the total stated |
|---|---|---|
| 13 | 12 | 13 |

The one miss: asked a second time about @alder_brackley and @orrin_ravensworth, the agent answered "5 records: 3
direct messages and 2 calls", counting the same people's other identities; their two app identities hold 3 (the
first answer said 3). Two further runs are left out: the measuring script left the page before they finished, and
they hold no answer. Answers took 26 to 105 s.

After the instructions kept to the identities a question names (release abb17d87), the same question asked
twice more answered 3 both times, each citing 3 records.

## Cross questions, phones and money, tool layer, 2026-11-03 (`tool-layer-cross-2026-11-03.jsonl`)

20 questions with known answers, written by hand in `backend/tests/test_agent_cross_evaluation.py`, on one synthetic
case holding two handsets of one person (one with messages and calls, one with bank notifications, a one-time code
and an exchange app), three more people, and a ledger of five payments from that person's account (one p3). They
cover money and contact between two people (whole span, one month, a pair with no money, a person only in another
case), the conversation around a payment (anchored on the phone alert, no conversation with each reason, widened to a
week), a purpose reading drafted and one refused for quoting outside the window, the alerts that match rows, the
leads with missing account and missing period, a control claim that holds, one for a person with no phone and one
for a month with nothing tying the account to the phone, search, a person's numbers, and one day across phone and
ledger.

| Setting | Questions | Known total stated | Exactly the known records cited | Extra check (amounts, outcome, reason, label) | Refused with the boundary, no records |
|---|---|---|---|---|---|
| All data | 20 | 20 | 20 | 20 | not applicable |
| Significant | 20 | not applicable | not applicable | not applicable | 20 |

Before this release the score was 0 of 20: none of the tools these questions use existed (release 24fa46e3).
