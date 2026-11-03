"""Guided investigative workflows: the ten scenarios of the agent report, and seven more (agent-workflows A).

Source: ``headless/reports/Loupe agent investigative workflows.md``, "Ten scenarios show the joined platform at work"
and "Seven more scenarios". Each workflow is a named starting question, the tool sequence the scenario lists (by the
tool names this build registers), what becomes a proposal, and what a person confirms. Starting one adds its plan to
the agent's prompt for that run and records the workflow on the run (``AgentRun.extra_metadata["workflow"]``).

The workflow never makes the agent conclude. Its outputs are proposals (the ``propose_*`` tools, the ``draft_*``
tools), and when a proposal tool is not in this build the answer lists the item under "Proposals for a person to
confirm" instead. Every workflow answer ends with "Not examined": each step that could not run (tool missing, no
data of that kind in the case, budget), in the same words whatever the reason.

Readiness (``readiness``) is measured, not assumed: the case's own counts of ledger rows, financial source documents,
phones, evidence documents, dossiers and timeline entries, read in one read-only session, against what each
workflow needs. A workflow whose needs no case meets is "not possible on current data" with the counts that show it.

Decisions (agent-workflows, 2026-11-03; each says what would reverse it):

- W-a The plan goes into the system prompt (beside the mandate), not into a fixed tool script. The scenarios are
  investigative: the order holds, but each step's arguments come from the previous step's results, which only the
  model can read. Reverse if a measured run shows the model skipping listed steps on more than 1 in 5 workflow runs;
  then the runner should call the deterministic steps itself.
- W-b Steps name the tools this build registers. The report's names map as follows: ``get_money_between`` is
  agent-ledger's tool (``get_contact_and_money_between`` adds the contact side), ``read_conversation_window`` is
  ``get_payment_conversation``, ``get_pattern_grid`` is ``get_day_activity`` per day (no grid tool exists).
  Reverse if a grid tool is registered.
- W-c A step whose tool is not registered stays in the plan, marked "not in this build", and the answer reports it
  under "Not examined". Reverse never: hiding a step would present a partial workflow as whole (rule 2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SCHEMA = "loupe.agent.workflows/1"

# Kinds of case data a step reads. Counted per case by ``case_counts``.
DATA_KINDS = {
    "ledger": "ledger rows (payments read from statements)",
    "phones": "phone extractions",
    "documents": "evidence documents other than statements and phone files",
    "dossiers": "people dossiers (a person on People; the person tools need one)",
    "timeline": "case timeline entries",
}


@dataclass(frozen=True)
class Step:
    tool: str
    why: str
    needs: tuple[str, ...] = ()
    optional: bool = False
    by_person: bool = False  # a screen step a person takes (e.g. Red cell on a Workspace theory), not a tool call


@dataclass(frozen=True)
class Workflow:
    id: str
    number: int
    title: str
    question: str
    starting_question: str
    steps: tuple[Step, ...]
    proposals: tuple[tuple[str, str], ...]  # (tool, what it proposes)
    person_confirms: str
    rules: tuple[str, ...]
    needs: tuple[str, ...]           # data kinds without which the workflow cannot run at all
    min_phones: int = 0
    adds_requirement: str | None = None  # the seven more scenarios: the one requirement each adds
    requirement_met_by: tuple[str, ...] = ()  # tools / modules in this build that meet it
    not_modelled: str | None = None  # data the ledger or phones do not model at all
    extra: bool = False

    @property
    def tools(self) -> list[str]:
        return [s.tool for s in self.steps if not s.by_person] + [t for t, _ in self.proposals]


PROPOSE_RULE = ("Outputs are proposals, never conclusions: record each with the proposal tool named, and when it is "
                "not in your tool list, put it under 'Proposals for a person to confirm' with its citations.")

S = Step
WORKFLOWS: tuple[Workflow, ...] = (
    Workflow(
        id="last-proof-of-life", number=1, title="Last proof of life",
        question="When was the person last demonstrably alive and acting, and who was with them?",
        starting_question=("When was {person} last demonstrably alive and acting, and who was with them? Separate the "
                           "last human-initiated event from the last device event."),
        steps=(
            S("get_person_phones", "the person's phones and the identities linked to them", ("phones", "dossiers")),
            S("get_day_activity", "the last days on the person's phone: human-initiated events (outgoing messages, "
              "unlocks, typed input) apart from passive ones (incoming messages, background sync)", ("phones",)),
            S("get_money_signal_matches", "the last card payments bound to the alerts that give their time "
                                          "(connection 1)", ("phones", "ledger"), optional=True),
            S("get_financial_transactions", "the last card-present payment and cash withdrawal on the ledger",
              ("ledger",), optional=True),
            S("get_together_apart", "other people's phones against the person's in the last window", ("phones",),
              optional=True),
            S("get_payment_conversation", "the last exchanges around the last payment", ("phones", "ledger"),
              optional=True),
            S("get_analysis_results", "approach 3 (deletion_timeline): anything removed afterwards", ("phones",),
              optional=True),
            # Approach 13 (incident window) is a screen over the Day view's lanes; get_day_activity reads them.
            S("get_timeline_events", "the case timeline around the anchor", (), optional=True),
        ),
        proposals=(("propose_timeline_addition", "the last human-initiated event and the last device event, each "
                                                 "cited"),
                   ("propose_workspace_entry", "the supporting and the undercutting reading of each event")),
        person_confirms="which event is the last proof of life and every attribution behind it",
        rules=("List 'last human-initiated event' and 'last device event' separately.",
               "A payment after the presumed time is evidence that someone used the card, not that the person was "
               "alive; it opens the question of who controlled the account.",
               "Places are where the phone recorded itself, not the person. Gaps say 'no record' and why.",
               "State the supporting and the undercutting reading of each event."),
        needs=("phones",), min_phones=1,
    ),
    Workflow(
        id="hidden-assets", number=2, title="Hidden assets",
        question="Which accounts and assets does the subject hold that a declaration omits, and does their "
                 "lifestyle exceed their proven income?",
        starting_question=("Which accounts does {person} hold that this case's financial records do not, and does "
                           "verified spending exceed verified income month by month?"),
        steps=(
            S("get_money_signal_leads", "institutions and endings the phone evidences (apps, alerts, codes) and "
                                        "their status against the case's accounts", ("phones",), optional=True),
            S("get_financial_coverage", "the accounts and periods the ledger holds", ("ledger",)),
            S("get_statement_continuity", "missing months on held accounts (connection 2)", ("ledger",)),
            S("get_account_mentions", "transfers to the subject's own accounts held elsewhere", ("ledger",)),
            S("analyze_financial_transactions", "verified income against verified spending, by month and category (population=verified)",
              ("ledger",)),
            S("search_documents", "the declaration or statement of means, if the case holds it", ("documents",),
              optional=True),
        ),
        proposals=(("propose_lead_card", "each account seen on the phone and absent from the financial records"),
                   ("propose_judgement_call", "each missing statement month")),
        person_confirms="each lead card before any request, and each control claim before an account is treated as "
                        "the subject's",
        rules=("Alert amounts are p4 and never added to an asset figure.",
               "Income and spending use verified p0-p2 rows only.",
               "Any figure for missing months is labelled 'estimate, not measured'.",
               "Say 'absent from the financial records in this case', never 'concealed'."),
        needs=("ledger",),
    ),
    Workflow(
        id="carer-abuse", number=3, title="Power-of-attorney and carer abuse",
        question="Which transfers from an elderly person's account did that person authorise, and who executed the "
                 "rest?",
        starting_question=("Which transfers from {person}'s accounts went to {other} or their associates, which phone "
                           "received each alert and code, and where was {other}'s phone at the time?"),
        steps=(
            S("get_money_between", "money from the account holder to the carer and associates", ("ledger",)),
            S("get_contact_and_money_between", "contact between the two beside the money", ("phones", "ledger"),
              optional=True),
            S("get_money_signal_matches", "which handset received each alert and code; a switch of alerts from one "
                                          "phone to the other from a date", ("phones", "ledger")),
            S("draft_control_claim", "the control claim for the account, strands for and against", ("phones",
                                                                                                    "ledger", "dossiers")),
            S("get_together_apart", "whether the carer's phone was at the holder's home when online transfers were "
                                    "made", ("phones",), optional=True),
            S("get_payment_conversation", "what was said around each transfer ('you said I could have it')",
              ("phones", "ledger")),
            S("draft_payment_purpose", "the stated purpose of each transfer, quoting the messages", ("phones",
                                                                                                    "ledger")),
        ),
        proposals=(("draft_control_claim", "the control claim, strands for and against"),
                   ("draft_payment_purpose", "each transfer's stated purpose"),
                   ("propose_workspace_entry", "the gift claim found in messages, with equal prominence")),
        person_confirms="the control claim and each purpose reading",
        rules=("A gift claim in the messages is shown with equal prominence to the evidence against it.",
               "The stated purpose of each transfer is a model reading until a person confirms it."),
        needs=("ledger", "phones"), min_phones=1,
    ),
    Workflow(
        id="procurement-kickbacks", number=4, title="Procurement kickbacks",
        question="Did a vendor pay an official for a contract, and through whom?",
        starting_question=("Trace the chain from meeting to award to payment to cash between {person} and {other}: "
                           "where they met, the award date, the payments and the onward money."),
        steps=(
            S("get_together_apart", "meetings where the two phones were co-located", ("phones",)),
            S("search_documents", "the tender and award dates", ("documents",)),
            S("get_financial_transactions", "the public body's payments to the vendor", ("ledger",)),
            S("get_money_between", "the vendor's onward payments to the official, an intermediary or cash",
              ("ledger",)),
            S("get_payment_conversation", "the messages around each leg (connection 4)", ("phones", "ledger")),
            S("get_analysis_results", "approach 4 (awareness): read times and reply delays for who knew",
              ("phones",), optional=True),
        ),
        proposals=(("propose_workspace_entry", "the code-word glossary, term by term (term, meaning, speaker, "
                                               "citations)"),
                   ("propose_link", "each chain link to its source"),
                   ("draft_payment_purpose", "the stated purpose of each leg")),
        person_confirms="the glossary, each chain link and any intermediary identity",
        rules=("Each chain link shows its own class: co-location (investigative, potential only), award (document "
               "page), vendor payment (ledger row), personal transfer (row or p4 alert), message (record).",
               "Decoded meanings stay model readings until confirmed."),
        needs=("ledger", "phones", "documents"), min_phones=2,
    ),
    Workflow(
        id="expense-fraud", number=5, title="Expense and travel fraud",
        question="Did the claimed dinner or trip happen as claimed?",
        starting_question=("Did the expense claimed on {date} happen as claimed: the receipt, the card line, the card "
                           "alert's time and where {person}'s phone was?"),
        steps=(
            S("search_documents", "the receipt and the expense claim (merchant, amount, date, attendees)",
              ("documents",)),
            S("get_financial_transactions", "the card line", ("ledger",)),
            S("get_money_signal_matches", "the card alert's time", ("phones", "ledger"), optional=True),
            S("get_day_activity", "where the phone was at that time", ("phones",), optional=True),
            S("get_payment_conversation", "the messages that bear on the stated attendees", ("phones", "ledger"),
              optional=True),
            S("evaluate_statement", "the person-confirmed claim against the phones", ("phones",), optional=True),
        ),
        proposals=(("propose_workspace_entry", "the receipt reading as a claim, cited to its page"),
                   ("propose_link", "the receipt to the card line")),
        person_confirms="the receipt reading and the outcome",
        rules=("The receipt reading is model work until confirmed. The card line keeps its proof class; the alert "
               "time is p4. Place is investigative.",
               "Outcomes include 'no record' with its reason (for example no location data that evening)."),
        needs=("ledger", "documents"),
    ),
    Workflow(
        id="insider-trading", number=6, title="Insider trading",
        question="Did the trader act on inside information, and who passed it?",
        starting_question=("Set {person}'s trades against the calls and messages of the information chain, to the "
                           "minute, with time zones explicit."),
        steps=(
            S("get_financial_transactions", "brokerage executions (instrument, quantity, execution time)",
              ("ledger",)),
            S("get_day_activity", "call starts and ends and message times on the chain's phones", ("phones",)),
            S("get_payment_conversation", "messages around each trade", ("phones", "ledger")),
            S("get_analysis_results", "approach 4 (awareness): read and reply events", ("phones",), optional=True),
            S("draft_control_claim", "nominee accounts (connection 3)", ("phones", "ledger", "dossiers"), optional=True),
        ),
        proposals=(("propose_workspace_entry", "each 'order placed during call' relation with its two citations"),),
        person_confirms="each chain link and any nominee control claim",
        rules=("Time zones are explicit: the raw value and the offset side by side.",
               "Never state that someone knew; report read and reply events."),
        needs=("ledger", "phones"), min_phones=1,
        not_modelled=("Brokerage trades: the ledger holds payments, not instrument and quantity rows, so a trade's "
                      "execution time and instrument cannot be read."),
    ),
    Workflow(
        id="payment-scam-victim", number=7, title="Payment-scam victims",
        question="What was the victim told before each payment, where did the money go, and which receiving "
                 "accounts recur?",
        starting_question=("For each outgoing payment from {person}'s accounts, what was {person} told before it, and "
                           "which receiving accounts recur?"),
        steps=(
            S("get_financial_transactions", "the victim's outgoing payments", ("ledger",)),
            S("get_payment_conversation", "the window before each payment: the script and instructions",
              ("phones", "ledger")),
            S("get_money_between", "the receiving accounts and the money to each", ("ledger",)),
            S("get_account_mentions", "receiving accounts named elsewhere in the case", ("ledger",)),
            S("draft_payment_purpose", "what the victim was told, quoted, for each payment", ("phones", "ledger")),
        ),
        proposals=(("draft_payment_purpose", "each 'told before payment' pairing"),
                   ("propose_judgement_call", "who the other side of each payment is (a mule flag is a lead)")),
        person_confirms="each pairing and every mule identification",
        rules=("Each 'told before payment' pairing is a judgement call. A mule flag is a lead, never a finding.",
               "Cross-victim linkage is limited to this case; other cases are not searched."),
        needs=("ledger", "phones"), min_phones=1,
    ),
    Workflow(
        id="drug-proceeds", number=8, title="Drug-supply turnover and proceeds",
        question="What turnover and benefit do deal-line volume and cash deposits support?",
        starting_question=("What turnover do the deal line's message volume and {person}'s cash deposits support, "
                           "with every assumption set by a person?"),
        steps=(
            S("get_analysis_results", "approach 5 (device_users): who used the deal line over which periods",
              ("phones",)),
            S("get_together_apart", "attribution of the line to people over periods", ("phones",), optional=True),
            S("get_day_activity", "deal conversations and flare texts per day (no grid tool: one day per call)",
              ("phones",)),
            S("analyze_financial_transactions", "cash deposits and money transfers per period (population=verified)", ("ledger",)),
            S("propose_assumption", "each assumption (price per deal, share of messages that are deals, deals per "
                                    "message) with its source", ()),
        ),
        proposals=(("propose_assumption", "each calculator assumption with its stated source"),
                   ("propose_workspace_entry", "the line attribution over periods")),
        person_confirms="every assumption and the line attribution",
        rules=("The calculator multiplies; never compute a turnover yourself.",
               "The turnover range is labelled 'estimate, not measured'. Deposits use verified p0-p2 rows only."),
        needs=("phones", "ledger"), min_phones=1,
    ),
    Workflow(
        id="staged-accident", number=9, title="Staged-accident insurance fraud",
        question="Were the 'strangers' in a collision organised, and who paid them?",
        starting_question=("Were {person} and {other} together before the collision on {date}, and did money move to "
                           "them after the insurer paid?"),
        steps=(
            S("get_together_apart", "whether the claimants' phones were together before the accident", ("phones",)),
            S("get_contact_and_money_between", "contact and money between the claimants", ("phones",)),
            S("search_case", "planning messages across the phones", ("phones",)),
            S("get_analysis_results", "approach 2 (message_reconciliation): messages present on one handset and "
                                      "deleted on another", ("phones",), optional=True),
            S("get_money_between", "payments from an organiser to the claimants after the payout", ("ledger",)),
            S("search_documents", "the claim files", ("documents",), optional=True),
        ),
        proposals=(("propose_workspace_entry", "each co-location reading with the observations against it"),
                   ("propose_link", "each organiser link")),
        person_confirms="each co-location reading and each organiser link",
        rules=("Co-location is potential only; list the observations against it beside those for it.",
               "Planning-message readings are model work. Cross-case linkage is not searched."),
        needs=("phones", "ledger"), min_phones=2,
    ),
    Workflow(
        id="defence-review", number=10, title="Defence and review",
        question="Does the other side's timeline hold up, and what in the material points away from their "
                 "conclusion?",
        starting_question=("Test the other side's timeline line by line: which of its conclusions rest on unconfirmed "
                           "judgement calls or model readings, where are the gaps, and what points away?"),
        steps=(
            S("get_casework", "the other side's timeline as confirmed claims, and the case's theories", ()),
            S("get_timeline_events", "the case timeline", (), optional=True),
            S("evaluate_statement", "each person-confirmed claim against the phones", ("phones",), optional=True),
            S("get_judgement_calls", "which conclusions rest on unconfirmed judgement calls", ("ledger",),
              optional=True),
            S("get_decisions", "the decisions behind ledger rows, with who made them", ("ledger",), optional=True),
            S("get_financial_coverage", "gaps as 'no record, and why'", ("ledger",), optional=True),
            S("draft_control_claim", "attribution claims checked for strands against", ("phones", "ledger", "dossiers"),
              optional=True),
            S("red_cell", "a person runs Red cell on the theory in Workspace: the away-from-the-suspect sweep",
              (), optional=True, by_person=True),
        ),
        proposals=(("propose_workspace_entry", "each finding citing both the other side's statement and the source "
                                               "that bears on it, both quoted"),
                   ("propose_link", "contradicting sources to the claim they bear on")),
        person_confirms="every claim extracted from the other side's timeline before it is evaluated",
        rules=("Quote both the other side's statement and the source verbatim.",
               "Cell-site or phone points are where a phone recorded itself, never a person's presence."),
        needs=(),
    ),
    # The seven more scenarios: each adds one requirement (report, "Seven more scenarios each add one requirement").
    Workflow(
        id="county-lines", number=11, title="County lines", extra=True,
        question="Who ran the deal line over which periods, and does exploitation evidence sit beside supply?",
        starting_question=("Who used the deal line over which periods (number, rebrand and handset history), and what "
                           "debt or threat messages sit beside the supply messages?"),
        steps=(
            S("get_analysis_results", "approach 5 (device_users): users of the line over periods", ("phones",)),
            S("get_person_phones", "the identities on each phone", ("phones", "dossiers")),
            S("search_case", "debt and threat messages beside supply messages", ("phones",)),
        ),
        proposals=(("propose_workspace_entry", "the line's lineage over periods and the exploitation evidence"),),
        person_confirms="the line attribution and each exploitation reading",
        rules=("The durable identity is the deal line, not the handset.",
               "Exploitation evidence is shown beside supply evidence (s.45 defence)."),
        needs=("phones",), min_phones=1,
        adds_requirement="line lineage: the deal line's number and handset history as the durable identity",
        requirement_met_by=("services.phone_analysis.device_users", "get_analysis_results"),
    ),
    Workflow(
        id="coercive-control", number=12, title="Coercive control", extra=True,
        question="What bank-control events and monitoring-app installs and logins fall inside the offence dates?",
        starting_question=("List the economic-abuse events against {person}: bank control events beside monitoring-app "
                           "installs and logins, from 29 December 2015, and post-separation only from 5 April 2023."),
        steps=(
            S("get_financial_transactions", "bank control events on the complainant's accounts", ("ledger",)),
            S("search_case", "monitoring-app installs and logins on the complainant's phone", ("phones",)),
            S("get_day_activity", "the days of each event", ("phones",), optional=True),
        ),
        proposals=(("propose_timeline_addition", "each economic-abuse event inside the date limits"),),
        person_confirms="each event and whether it is post-separation",
        rules=("Hard date filters: nothing before 29 December 2015; post-separation conduct only from 5 April 2023. "
               "Events outside them are listed as outside, never counted.",),
        needs=("ledger", "phones"), min_phones=1,
        adds_requirement="an economic-abuse lane and hard date filters (29 Dec 2015; post-separation from 5 Apr 2023)",
        requirement_met_by=("services.agent.workflows.COERCIVE_CONTROL_DATES",),
    ),
    Workflow(
        id="human-trafficking", number=13, title="Human trafficking", extra=True,
        question="Who controlled the victim's phone and the money from advert to controller account?",
        starting_question=("Who had the means to operate {person}'s phone and accounts, and where did the money go "
                           "from booking to controller?"),
        steps=(
            S("draft_control_claim", "device is not person: the phone-to-person link with strands against",
              ("phones", "ledger", "dossiers")),
            S("get_analysis_results", "approach 5 (device_users): signs of more than one user", ("phones",)),
            S("get_money_between", "buyer payments to the controller account", ("ledger",)),
        ),
        proposals=(("draft_control_claim", "each control claim"),),
        person_confirms="each control claim",
        rules=("Device does not equal person: a victim's phone is often run by the controller.",),
        needs=("phones", "ledger"), min_phones=1,
        adds_requirement="device is not person: the phone-to-person link carries its own strands for and against",
        requirement_met_by=("draft_control_claim",),
    ),
    Workflow(
        id="sanctions-evasion", number=14, title="Sanctions evasion", extra=True,
        question="What moved after the designation date, and who knew?",
        starting_question=("What payments involving {person} moved after the designation on {date}, and what read and "
                           "reply events show who was told?"),
        steps=(
            S("get_timeline_events", "the designation event on the person", ()),
            S("get_financial_transactions", "payments after the designation date", ("ledger",)),
            S("get_analysis_results", "approach 4 (awareness): read and reply events, the knowledge lane",
              ("phones",)),
        ),
        proposals=(("propose_timeline_addition", "the designation event, cited to its notice"),),
        person_confirms="the designation event and each knowledge reading",
        rules=("Never state that someone knew; report read and reply events.",),
        needs=("ledger",),
        adds_requirement="a designation event on a person and a knowledge lane",
        requirement_met_by=("propose_timeline_addition", "services.phone_analysis.awareness"),
    ),
    Workflow(
        id="money-laundering", number=15, title="Money laundering", extra=True,
        question="Set out the schedule in the indictment's own format, each cell with its proof class.",
        starting_question=("Build the schedule for {person}: contract, pickup, amount, receiving account and onward "
                           "wires, each cell with its proof class and citation."),
        steps=(
            S("get_financial_transactions", "the receiving accounts and onward wires", ("ledger",)),
            S("get_money_between", "money from each pickup to each receiving account", ("ledger",)),
            S("search_case", "pickup codes and banknote serial numbers in messages and documents", ()),
            S("build_table_artifact_from_rows", "the schedule, one column per field and a proof-class column", ()),
        ),
        proposals=(("propose_workspace_entry", "the schedule as a finding; pickup codes and serials as entities"),),
        person_confirms="each schedule row and each code or serial reading",
        rules=("Every cell carries its proof class (ledger row class, p4 alert, model reading, document page).",),
        needs=("ledger",),
        adds_requirement="banknote serials and pickup codes as entities, and an indictment-format schedule with "
                         "each cell's proof class",
        requirement_met_by=("build_table_artifact_from_rows",),
    ),
    Workflow(
        id="embezzlement", number=16, title="Embezzlement", extra=True,
        question="Which accounts and cards does the phone show that the books do not?",
        starting_question=("Which accounts and cards does {person}'s phone point to that this case's financial "
                           "records do not hold, and which months are missing?"),
        steps=(
            S("get_money_signal_leads", "accounts and periods the phone points to that the ledger lacks", ("phones",)),
            S("get_statement_continuity", "missing months on held accounts", ("ledger",)),
            S("get_account_mentions", "accounts named in the case that hold no statements", ("ledger",)),
        ),
        proposals=(("propose_lead_card", "each secret account lead"),
                   ("propose_judgement_call", "each missing month")),
        person_confirms="each lead card before any request",
        rules=("Say 'absent from the financial records in this case', never 'secret' or 'concealed'.",),
        needs=("phones", "ledger"), min_phones=1,
        adds_requirement="connection 2 in its purest form: phone-evidenced accounts the ledger lacks",
        requirement_met_by=("get_money_signal_leads", "get_statement_continuity"),
    ),
    Workflow(
        id="organised-retail-crime", number=17, title="Organised retail crime", extra=True,
        question="Which marketplace payout account joins the booster chats, the payments to boosters and the resale?",
        starting_question=("Which marketplace payout account receives the resale money, who had the means to operate "
                           "it, and which payments went from it to boosters?"),
        steps=(
            S("get_account_mentions", "the marketplace payout accounts named in the case", ("ledger",)),
            S("draft_control_claim", "who had the means to operate the payout account", ("phones", "ledger", "dossiers")),
            S("get_money_between", "payments from the payout account to boosters", ("ledger",)),
            S("search_case", "booster chats", ("phones",), optional=True),
        ),
        proposals=(("draft_control_claim", "the payout account's control claim"),
                   ("propose_link", "the payout account to the chats and payments")),
        person_confirms="the payout account's control claim",
        rules=("The payout account is the attribution anchor; each link carries its own class.",),
        needs=("ledger",),
        adds_requirement="the marketplace payout account as the attribution anchor",
        requirement_met_by=("get_account_mentions", "draft_control_claim"),
    ),
)

BY_ID = {w.id: w for w in WORKFLOWS}

# Scenario 12's requirement (built here): the dates the coercive-control offence counts from (CPS CCB guidance).
COERCIVE_CONTROL_DATES = {"offence_from": "2015-12-29", "post_separation_from": "2023-04-05"}


def get(workflow_id: str) -> Workflow:
    try:
        return BY_ID[workflow_id]
    except KeyError:
        raise ValueError("No workflow %r. Known: %s." % (workflow_id, ", ".join(BY_ID))) from None


_TOOL_NAMES: dict[str, frozenset[str]] = {}


def registered_tool_names() -> frozenset[str]:
    """The agent tools this build registers (computed once per process, as the run record computes them)."""
    if "names" not in _TOOL_NAMES:
        from services.agent.tools import AgentToolContext, make_agent_tools
        _TOOL_NAMES["names"] = frozenset(t.name for t in make_agent_tools(AgentToolContext(case_id="{case_id}")))
    return _TOOL_NAMES["names"]


def render_block(w: Workflow, tools: Iterable[str] | None = None) -> str:
    """The workflow plan as the agent's prompt sees it. ``tools``: the registered names (a step whose tool is not
    among them is marked 'not in this build' and must be reported under Not examined)."""
    have = frozenset(tools) if tools is not None else registered_tool_names()
    lines = ["Guided workflow %d: %s." % (w.number, w.title),
             "The question: %s" % w.question,
             "Follow these steps in order. Use each step's results to choose the next step's arguments. A step marked "
             "optional runs when the case holds its data; say so when it does not."]
    for i, s in enumerate(w.steps, 1):
        mark = []
        if s.optional:
            mark.append("optional")
        if s.by_person:
            mark.append("a person does this on screen; suggest it, do not claim it was done")
        elif s.tool not in have:
            mark.append("not in this build: report it under Not examined")
        lines.append("%d. %s: %s%s" % (i, s.tool, s.why, " (%s)" % "; ".join(mark) if mark else ""))
    lines.append(PROPOSE_RULE)
    for tool, what in w.proposals:
        lines.append("- %s: %s%s" % (tool, what, "" if tool in have else " (not in this build: list it instead)"))
    lines.append("A person confirms %s." % w.person_confirms)
    lines.extend("Rule: %s" % r for r in w.rules)
    if w.not_modelled:
        lines.append("Not modelled in Loupe: %s Say so in the answer." % w.not_modelled)
    lines.append("End the answer with three headed parts: 'Proposals made' (each proposal tool call and what it "
                 "recorded), 'For a person to confirm' (each item, cited), and 'Not examined' (each step that did not "
                 "run or ran on no data, and why, in plain words). Never present the workflow's result as a "
                 "conclusion.")
    return "\n".join(lines)


def case_counts(conn, case_id) -> dict[str, int | None]:
    """The case's own counts of each data kind, read-only. A missing table counts 0 (a test schema)."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    queries = {
        "ledger": "SELECT count(*) FROM financial_transactions WHERE case_id = :c",
        "financial_sources": "SELECT count(*) FROM financial_source_documents WHERE case_id = :c",
        "phones": "SELECT count(*) FROM phone_extractions WHERE case_id = :c AND standing <> 'superseded'",
        "documents": "SELECT count(*) FROM evidence_files e WHERE e.case_id = :c AND e.cellebrite_file_id IS NULL "
                     "AND e.cellebrite_report_key IS NULL AND (e.source_type IS NULL OR e.source_type NOT IN ('phone_extraction', "
                     "'phone_file', 'phone_text', 'cellebrite')) AND NOT EXISTS (SELECT 1 FROM financial_source_documents f "
                     "WHERE f.case_id = e.case_id AND f.evidence_file_id = e.id)",
        "dossiers": "SELECT count(*) FROM case_profiles WHERE case_id = :c",
        "timeline": "SELECT count(*) FROM timeline_entries WHERE case_id = :c",
    }
    out: dict[str, int | None] = {}
    for kind, sql in queries.items():
        try:
            with conn.begin_nested():
                out[kind] = int(conn.execute(text(sql), {"c": str(case_id)}).scalar() or 0)
        except DBAPIError as exc:
            # A missing table (a test schema) counts 0; any other failure is None, "could not be counted", never
            # shown as "the case holds none".
            missing = "does not exist" in str(getattr(exc, "orig", exc)) or "no such table" in str(exc)
            if not missing:
                logger.warning("Workflow readiness could not count %s for case %s: %s", kind, case_id, exc)
            out[kind] = 0 if missing else None
    return out


def assess(w: Workflow, counts: dict[str, int], tools: Iterable[str] | None = None) -> dict[str, Any]:
    """Whether ``w`` can run on a case with ``counts``: ready (every step runs); partial (a workflow need is met but
    some step cannot run, for want of its data or its tool, and is reported as not examined); not_possible (a kind
    the workflow needs is absent, too few phones, or the data is not modelled); unknown (a count failed). Counts,
    not guesses."""
    have = frozenset(tools) if tools is not None else registered_tool_names()
    uncounted = sorted(k for k in set(w.needs) | {k for s in w.steps for k in s.needs} if counts.get(k, 0) is None)
    if uncounted:
        return {"id": w.id, "number": w.number, "title": w.title, "status": "unknown",
                "reasons": ["the case's %s could not be counted just now; try again" % DATA_KINDS.get(k, k)
                            for k in uncounted],
                "tools_missing": [], "steps_that_run": 0, "steps": []}
    missing_data = [k for k in w.needs if not counts.get(k)]
    if w.min_phones and counts.get("phones", 0) < w.min_phones and "phones" not in missing_data:
        missing_data.append("phones")
    steps = []
    for s in w.steps:
        absent = [k for k in s.needs if not counts.get(k)]
        in_build = s.by_person or s.tool in have
        steps.append({"tool": s.tool, "why": s.why, "optional": s.optional, "by_person": s.by_person,
                      "in_build": in_build, "data_missing": absent,
                      "runs": in_build and not absent and not s.by_person})
    tools_missing = sorted({s["tool"] for s in steps if not s["in_build"]} |
                           {t for t, _ in w.proposals if t not in have})
    reasons = []
    for k in missing_data:
        if k == "phones" and w.min_phones > 1:
            reasons.append("needs %d phones; the case holds %d" % (w.min_phones, counts.get("phones", 0)))
        else:
            reasons.append("the case holds no %s" % DATA_KINDS.get(k, k))
    if w.not_modelled:
        reasons.append(w.not_modelled)
    if missing_data or w.not_modelled:
        status = "not_possible"
    elif tools_missing or any(not s["runs"] for s in steps if not s["by_person"]):
        status = "partial"
    else:
        status = "ready"
    return {"id": w.id, "number": w.number, "title": w.title, "status": status, "reasons": reasons,
            "tools_missing": tools_missing, "steps_that_run": sum(1 for s in steps if s["runs"]),
            "steps": steps}


def catalogue(counts: dict[str, int] | None = None, tools: Iterable[str] | None = None) -> dict[str, Any]:
    """Every workflow for the picker, each with its readiness on ``counts`` when given."""
    items = []
    for w in WORKFLOWS:
        item = {"id": w.id, "number": w.number, "title": w.title, "question": w.question,
                "starting_question": w.starting_question, "extra": w.extra,
                "steps": [s.tool for s in w.steps], "proposals": [t for t, _ in w.proposals],
                "person_confirms": w.person_confirms, "adds_requirement": w.adds_requirement,
                "requirement_met_by": list(w.requirement_met_by)}
        if counts is not None:
            item["readiness"] = assess(w, counts, tools)
        items.append(item)
    return {"schema": SCHEMA, "counts": counts, "workflows": items, "total": len(items)}
