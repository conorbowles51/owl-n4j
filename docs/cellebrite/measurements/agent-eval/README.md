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

## Ledger questions, tool layer, 2026-11-03 (`ledger-tool-layer-2026-11-03.jsonl`)

12 questions on two live cases (BNB2, read only, and the verification case), asked through the agent's own tools
with the run's case by `backend/scripts/financial_agent_ledger_eval.py`. Each known answer is computed by plain SQL in
the script, independently of the code under test. The file holds scores only, never case values.

| Tree | Score | Why the misses missed |
|---|---|---|
| before (38f6bdbc) | 0 of 12 | 8 had no tool (money between two parties, judgement calls, decisions, statement continuity); the timeline had no investigator additions; an account total did not say how many open judgement calls it rests on; summed graph money did not say it is not a total |
| after (agent-ledger) | 12 of 12 | |

The questions: money between the one pair of BNB2 accounts linked by reviewed identity, p0 to p2 and p3 apart; how
many open judgement calls that figure rests on; open judgement calls in the case; the calls on one payment; who
decided one payment and whether a model drafted it; the dates one account's statements cover; how many periods it has
(saved, in the run, left out); the investigator's Timeline additions; money out of one account with the open calls
it rests on; summed graph money marked not a total; decisions on a record of the verification case; judgement calls
of the verification case.
## Workflow questions, tool layer, 2026-11-03 (`tool-layer-workflows-2026-11-03.jsonl`)

30 questions, 3 for each of the ten guided workflows (`backend/services/agent/workflows.py`), written by hand in
`backend/tests/test_agent_workflow_evaluation.py` on the cross set's synthetic case. Each question is asked of a tool
its workflow lists, or of the workflow's readiness on the case's measured counts (ledger 5 rows, 2 phones, 0
documents other than the statement, 4 dossiers, 0 timeline entries). They cover the last record on a day and whether
it was the owner's action, the alert that times a card payment, phone-evidenced accounts the records lack, the
periods held, verified spending by month (the p3 row left out), money in one month, a control claim, the
conversation around a payment (two windows) and a leg with none, a together-and-apart test refused because no phone
owner is linked on People, a card line, one day's money and calls, every outgoing payment, a purpose reading drafted
and one refused, an analysis not yet run, casework with none, a claim not in this case, a month with a payment and no
statement, and six readiness answers (three ready, two not possible for want of documents, insider trading not
possible because trades are not modelled).

| Setting | Questions | Known answer stated | Exactly the known records cited | Extra check |
|---|---|---|---|---|
| All data | 30 | 30 | 30 | 30 |
| Significant (tool questions) | 24 refused with the boundary, no records | | | |

On 96640bde (before the workflows): 24 of 30. The 24 tool questions use tools already released and answer the same;
the 6 readiness questions have no answer, because no workflow catalogue existed.

## Trades and holdings, tool layer, 2026-11-04 (`trades-tool-layer-2026-11-04.jsonl`)

7 questions on BNB2's brokerage and fund statements and the verification case, asked through `get_trades` with the
run's case by `backend/scripts/financial_agent_trades_eval.py` on live (read-only sessions). Each known answer is
computed by plain SQL in the script: money from the cash ledger's own rows, counts from the security rows. The file
holds scores only, never case values.

| Tree | Score | Why the misses missed |
|---|---|---|
| before (d0ccabf5) | 0 of 7 | no tool: the agent's 59 tools read no trade, instrument, quantity or holding |
| after (36b8b32f) | 7 of 7 | |

The questions: how many trades the case holds; how many a model read and no person has confirmed; money paid into and
received from the most-traded fund (against its cash lines); the time of day of those orders (none is printed: every
trade says so); the latest holdings with their value; an account from another case ("That account is not in this
case."); trades in the verification case.

By hand against one printed statement (an Intercam April 2025 statement, page 3 and the position table): the fund's
4 trades, units bought and sold, money paid and received, and the position and value at the month end returned by
`get_trades` equal the print.
