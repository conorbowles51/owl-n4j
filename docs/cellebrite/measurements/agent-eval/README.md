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
