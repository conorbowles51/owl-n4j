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

## Model answers

Measured on live in the synthetic training case through the agent screen, signed in: see the cb-crossev status.
