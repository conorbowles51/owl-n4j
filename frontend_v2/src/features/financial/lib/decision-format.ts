/**
 * Reading a recorded decision for display.
 *
 * `financialAPI.getCaseDecisions` returns pages of `DecisionRecord`. Each one
 * is something that was decided about a piece of evidence in a case: a
 * duplicate hidden, a row set aside, a document's standing moved. This module
 * turns those records into English. It is the layer between the wire and both
 * the hook and the panel, and it exists so that neither of them has to hold an
 * opinion about what a stored word means.
 *
 * Four things it deliberately does not do.
 *
 * **It does not recompute `by_machine`.** The backend derives it once, by
 * comparing the actor's address against the reconciliation stage's, which sits
 * at a reserved `.invalid` domain no person's account can hold. `api.ts` says
 * why that derivation is not repeated here: a reader that got the comparison
 * wrong would show software moving a document as though an analyst had, which
 * is the most misleading thing this log could be made to say. So the flag is
 * read, not re-derived, and `readDecidedBy` is only about putting it into
 * words.
 *
 * **It does not order anything, and it does not treat adjacency as sequence.**
 * The page arrives newest first by a timestamp that is transaction-start time,
 * so two decisions written in one transaction carry it identically.
 * `subject_sequence` is authoritative within one subject and says nothing
 * across subjects. `DECISION_ORDER_IS_NOT_SEQUENCE` is the sentence that puts
 * that on screen, and nothing here sorts a page into an order it did not
 * arrive in.
 *
 * **It does not interpret `before` and `after`.** They are the writer's shape,
 * not this file's: a supersession records a status and a pointer, a
 * reclassification records a proof class either side, a purge records what was
 * about to stop existing and has no `after` at all. Reading them is a job for
 * whatever renders one decision in detail, and guessing at a shape here would
 * put a key from one writer in front of a record from another.
 *
 * **It does not decide which decisions matter.** `run-format.ts` has
 * `needsAttention` because a broken run is a fact about the ledger being
 * short. Every record here is a decision somebody or something already took
 * deliberately, and there is no member of the vocabulary that is by itself a
 * problem. Which of them matters is a question about the case.
 *
 * Narrowing goes through `narrow` in `ledger-format.ts`, so a word this build
 * has never heard of is handled the way it is handled everywhere else: named,
 * marked unrecognised, never rendered blank. The backend can add a member
 * without this build knowing it, and the vocabularies here are mirrors that
 * `api.decisions.test.ts` holds against the Python.
 */

import {
  ADJUDICATION_DECISIONS,
  ADJUDICATION_SUBJECTS,
  type AdjudicationDecision,
  type AdjudicationSubject,
  type DecisionRecord,
  type DecisionsResponse,
} from "../api"
import { narrow, type NarrowedTerm, type TermCopy } from "./ledger-format"
import { formatRunTime } from "./run-format"
import type { Badge } from "@/components/ui/badge"
import type { ComponentProps } from "react"

type BadgeVariant = NonNullable<ComponentProps<typeof Badge>["variant"]>

/**
 * Where these words came from, for the unrecognised copy.
 *
 * Not "the ledger". A decision is not a column on a transaction; it is an
 * appended record of something somebody did, and it outlives the row it was
 * about -- a purge writes its decision before it deletes its subject.
 */
export const DECISION_SOURCE = "the case's record of decisions"

/**
 * Why two decisions sitting next to each other did not necessarily happen in
 * that order.
 *
 * Held here as one string so the screen and the tests say the same thing, the
 * way `RUN_COUNTS_ARE_HISTORY` does for the counts on a run. The timestamp is
 * written at the start of the transaction that recorded the decision, so
 * several decisions taken in one act share it exactly. Within one subject the
 * order is real and is the numbering each record carries. Across subjects it
 * is not, and a screen that let a reader infer it would be inviting a claim
 * about who acted first that nothing in the record supports.
 */
export const DECISION_ORDER_IS_NOT_SEQUENCE =
  "Decisions taken in one act share a time exactly, so two entries about " +
  "different pieces of evidence are not in the order they happened. Within " +
  "one piece of evidence the numbering is the order, and it is reliable."

/* ------------------------------------------------------------------ *
 * What a decision was about
 * ------------------------------------------------------------------ */

/**
 * The kinds of thing a decision can be about.
 *
 * `evidence_file` is the one that names nothing financial, and it is why the
 * table dropped its `financial_` prefix: a file can be sent away from this
 * subsystem before any financial row exists to be the subject of the decision.
 */
const SUBJECT_COPY: Record<AdjudicationSubject, TermCopy> = {
  transaction: {
    label: "Transaction",
    description: "A single line of a statement, as it stands in the ledger.",
  },
  statement_period: {
    label: "Statement period",
    description:
      "One statement's span for one account: the rows between an opening and a closing balance.",
  },
  source_document: {
    label: "Source document",
    description:
      "A statement or other financial document, together with every row read out of it.",
  },
  account: {
    label: "Account",
    description: "An account the case has statements for.",
  },
  evidence_file: {
    label: "Evidence file",
    description:
      "A file as it arrived, before anything was read out of it. Not part of the financial ledger.",
  },
  phone_extraction: {
    label: "Phone report",
    description: "One phone report as it was read into the case, with every record and file it lists. Not part of the financial ledger.",
  },
  phone_identity: {
    label: "Phone number or account",
    description: "One number, email address or app account seen on the case's phones. Not part of the financial ledger.",
  },
  phone_record: {
    label: "Phone record",
    description: "One record of a phone report, such as a message, call or contact. Not part of the financial ledger.",
  },
  phone_analysis_result: {
    label: "Phone analysis result",
    description: "One result of an analysis of the phones, such as money a phone records, confirmed or rejected by a person. Not part of the financial ledger.",
  },
  phone_derived_text: {
    label: "Machine text from a phone",
    description: "Text a machine made from a phone file, such as a transcript of a voice note or text read from an image, corrected or confirmed by a person. Not part of the financial ledger.",
  },  security_row: {
    label: "Brokerage statement row",
    description: "One trade or holding read from a brokerage statement, corrected or confirmed by a person.",
  },
}

export function readDecisionSubject(
  raw: string
): NarrowedTerm<AdjudicationSubject> {
  return narrow(raw, ADJUDICATION_SUBJECTS, SUBJECT_COPY, DECISION_SOURCE)
}

/* ------------------------------------------------------------------ *
 * What was decided
 * ------------------------------------------------------------------ */

/**
 * Every member of the vocabulary, in words.
 *
 * Each description is written from the writer that produces the member, not
 * from the member's name. Two of them need that stated, because the names
 * point the wrong way on their own.
 *
 * `admit_financial_document` does **not** mean a document was admitted into
 * the ledger. It means a file the router held back, because it recognised bank
 * data and indexing a statement as prose turns its figures into searchable
 * text that no total can be traced to, was sent to that text pipeline anyway
 * by a named person. `financial` in the member's name describes the document,
 * not the destination, and nothing is admitted to the ledger by it.
 *
 * `explain_balance_failure` is not a disposition. It records a finding about
 * why an identity does not close, and it changes no status and never can: a
 * well-corroborated explanation of a weakly-proved document leaves it weakly
 * proved.
 */
const DECISION_COPY: Record<AdjudicationDecision, TermCopy> = {
  supersede_phone_extraction: {
    label: "Phone report retired in favour of a newer one",
    description:
      "A person retired this phone report and named the newer report of the same phone that replaces it, with a typed reason. Nothing was deleted: its records stay readable and are marked as from a replaced report.",
  },
  keep_printed_holders: {
    label: "Each statement keeps the holder printed on it",
    description:
      "This card or account is printed under different holder names on different statements. A person decided that each statement is filed under the name printed on it, and each such statement carries a judgement call. Who holds the account is not decided, and no name is merged or changed.",
  },
  set_account_identity: {
    label: "Account identifiers and case connections reviewed",
    description:
      "An investigator saved account identifiers or connected a reviewed person or business to an existing case entity. The supporting source or knowledge and prior values remain in the history. This does not merge accounts or create transactions.",
  },
  supersede_duplicate: {
    label: "Hidden as a duplicate",
    description:
      "Another copy of this document was kept in its place, so what they both contain is counted once instead of twice. Nothing was deleted and the call can be reversed.",
  },
  restore_document: {
    label: "Duplicate call reversed",
    description:
      "A document that had been hidden behind another copy was put back, and what it contains counts again. Rows that had been set aside for reasons of their own keep that standing; putting the document back does not overturn those.",
  },
  purge_duplicate: {
    label: "Deleted for good",
    description:
      "A duplicate document was deleted and cannot be brought back. This entry was written before the deletion and outlives it, so what was removed and who removed it stays readable.",
  },
  quarantine_row: {
    label: "Row set aside",
    description:
      "The row is out of every total, search and money flow the case reports. It is still on the record, and it can be reinstated.",
  },
  release_row: {
    label: "Row reinstated",
    description:
      "A row that had been set aside counts again. The grounds it was set aside on are kept here, because once a row is back in, the row itself is not allowed to carry them.",
  },
  explain_balance_failure: {
    label: "Balance failure explained",
    description:
      "A finding about why a statement's own figures do not add up. It records a view and moves nothing: however well the explanation holds, the document keeps the standing it had.",
  },
  reclassify_document: {
    label: "Standing of proof moved",
    description:
      "How well a document is proved was settled once its figures had been checked, which cannot be known when the document first arrives. Every total filters on this, so the standing before and after is kept here rather than changing quietly.",
  },
  set_counterparty_party: {
    label: "Payment counterparty link changed",
    description:
      "An investigator linked or unlinked selected payment readings to a reviewed party. Original names, amounts and proof classes remain unchanged; direct overrides and earlier decisions are retained.",
  },
  set_account_party: {
    label: "Account party link changed",
    description:
      "An investigator assigned or removed an account-party link with a reason. Original account details and earlier decisions remain unchanged.",
  },
  correct_transaction: {
    label: "Ledger amount corrected",
    description:
      "The original reading was retained and replaced by a corrected row with a new citation. Verification is recalculated separately.",
  },
  link_phone_identity: {
    label: "Phone identities linked as one person",
    description:
      "A person decided that two numbers or accounts belong to the same person, with a reason. Both stay as they were read; the link can be undone.",
  },
  unlink_phone_identity: {
    label: "Phone identity link undone",
    description:
      "A link between two numbers or accounts was undone. The earlier link and its reason stay in the history.",
  },
  reject_phone_identity_link: {
    label: "Suggested phone identity link rejected",
    description:
      "A person decided that two numbers or accounts the system suggested as one person are not linked, with a reason. The suggestion is not offered again; the rejection can be undone.",
  },
  restore_phone_identity_link: {
    label: "Rejected phone identity link restored",
    description:
      "A rejected suggestion is offered again. The rejection and its reason stay in the history.",
  },
  set_phone_identity_label: {
    label: "Name given to a phone identity",
    description:
      "A person named a number or account for this case. The names each phone held stay visible beside it.",
  },
  set_phone_owner: {
    label: "Phone owner set",
    description:
      "A person said which number or account belongs to the phone's owner, with a reason, where the report did not show it or showed it wrongly.",
  },
  set_phone_device_zone: {
    label: "Phone time zone set",
    description:
      "A person said which time zone the phone kept, with a reason. Times without their own zone are shown in it.",
  },
  set_phone_default_region: {
    label: "Phone home country set",
    description:
      "A person said which country the phone's local numbers belong to, so numbers written without a country code are read correctly.",
  },
  set_phone_clock_offset: {
    label: "Phone clock difference recorded",
    description:
      "A person recorded that the phone's clock ran fast or slow by a stated amount. The report's own times stay beside the adjusted ones.",
  },
  apply_phone_zone_to_offsetless: {
    label: "Zone applied to times with none",
    description:
      "Times the report wrote without a time zone are read in the zone a person chose. Each such time says it comes from this decision.",
  },
  allow_phone_external_processing: {
    label: "Outside processing allowed for a phone",
    description:
      "A person allowed this phone's material to go to an outside service, such as transcription or translation, with a reason. Without this decision nothing from the phone goes out.",
  },
  accept_phone_reconciliation_difference: {
    label: "Phone report difference accepted",
    description:
      "Part of a phone report did not match the report's own counts and was held back. A person accepted the difference, with a reason, so that part is read.",
  },
  set_phone_label: {
    label: "Phone renamed",
    description:
      "A person gave the phone the name the case uses for it. The name taken from the report file stays in the history.",
  },
  correct_phone_value: {
    label: "Phone record value corrected",
    description:
      "A value on one phone record was corrected, with a reason. The value read from the report stays visible beside it, and only the corrected value is used.",
  },
  mark_not_duplicate: {
    label: "Copy decision on a phone record",
    description:
      "A person decided whether this record is a copy of another message shown once. Separating it shows it as its own row; putting it back undoes that. Both stay in the history.",
  },
  confirm_phone_reading: {
    label: "System reading of a phone confirmed",
    description:
      "A person checked how the system read one kind of record on one phone, after viewing examples, and confirmed it.",
  },
  correct_phone_reading: {
    label: "System reading of a phone corrected",
    description:
      "A person said how one kind of record on one phone should be read instead, with a reason. The phone is read again; the records captured from the report are unchanged.",
  },
  correct_security_row: {
    label: "Brokerage row value corrected",
    description:
      "A person corrected a value of a trade or holding read from a brokerage statement, with a reason. The value as read stays visible beside it, and only the corrected value is used.",
  },
  confirm_security_row: {
    label: "Brokerage row reading confirmed",
    description:
      "A person confirmed a value of a trade or holding as read from a brokerage statement. Until then a model's reading is shown as the model's.",
  },
  confirm_phone_result: {
    label: "Phone analysis result confirmed",
    description:
      "A person confirmed one result of a phone analysis. The result and the data it came from are unchanged.",
  },
  reject_phone_result: {
    label: "Phone analysis result rejected",
    description:
      "A person rejected one result of a phone analysis, with a reason. It stays visible as rejected.",
  },
  not_pursue_phone_result: {
    label: "Phone analysis lead not pursued",
    description:
      "A person decided not to follow one result of a phone analysis, with a reason. This says nothing about whether the result is right; the result and the data it came from are unchanged.",
  },
  undo_phone_result_decision: {
    label: "Decision on a phone match undone",
    description:
      "A person undid their last confirm or reject of a match between a phone alert and a payment. The match is back to how it stood before; the earlier decision stays in this record.",
  },
  attach_transaction_place: {
    label: "Place attached to a payment",
    description:
      "A person attached a place, a point with a radius, to a payment, with a reason. The payment itself is unchanged.",
  },
  remove_transaction_place: {
    label: "Place removed from a payment",
    description:
      "A place attached to a payment was removed. The earlier place stays in the history.",
  },
  place_text_place: {
    label: "Written place placed on the map",
    description:
      "A person placed a place written on a phone record (a calendar location, a check-in or an address) on the map, a point with a radius, with a reason. It shows what the record points to, never that the phone was there. The phone record itself is unchanged.",
  },
  remove_text_place: {
    label: "Written place taken off the map",
    description:
      "A place a person had put on the map for a written place on a phone record was removed. The earlier placement stays in the history.",
  },
  dispute_check_item: {
    label: "Statement check item marked wrong",
    description:
      "A person marked one item of a statement check as wrong, with a reason. The check's computed outcome is not changed by it.",
  },
  withdraw_check_item_dispute: {
    label: "Statement check mark withdrawn",
    description:
      "A mark saying a statement check item is wrong was withdrawn. The mark and its reason stay in the history.",
  },
  correct_machine_text: {
    label: "Machine text corrected",
    description:
      "A person corrected text a machine made from a phone file, such as a transcript or text read from an image, with a reason. The machine text stays visible beside it, and only the corrected text is searched.",
  },
  confirm_machine_text: {
    label: "Machine text confirmed",
    description:
      "A person confirmed text a machine made from a phone file after it was shown to them. The text is unchanged and is marked as checked by that person.",
  },
  admit_financial_document: {
    label: "Sent out for text processing",
    description:
      "A file recognised as bank data was held back, and a named person chose to send it for text processing anyway. Its figures become searchable text and will not appear in any total. Read carefully: nothing was admitted to the ledger here.",
  },
}

/**
 * Colours follow the ledger's, so the same event reads the same on both
 * screens: a row set aside badges amber here because it badges amber there,
 * and one reinstated takes the colour an admitted row has. `warning` is not
 * used for any member, because `LedgerTable` reserves it for "this build
 * cannot read this value", which is the case below.
 *
 * `purge_duplicate` takes the solid `destructive` rather than the softer
 * `danger` for one reason: it is the only member in the vocabulary that cannot
 * be undone. Every other disposition here has a reversal, or is a finding that
 * changed nothing.
 *
 * `Badge` falls through to its loud `default` variant for any key a map does
 * not carry, so a member missing from this table would render as the most
 * important thing on the screen. `Record<AdjudicationDecision, ...>` makes the
 * compiler notice instead.
 */
const DECISION_VARIANT: Record<AdjudicationDecision, BadgeVariant> = {
  supersede_duplicate: "slate",
  restore_document: "success",
  purge_duplicate: "destructive",
  quarantine_row: "amber",
  release_row: "success",
  explain_balance_failure: "info",
  reclassify_document: "info",
  correct_transaction: "info",
  set_account_party: "info",
  set_counterparty_party: "info",
  set_account_identity: "info",
  keep_printed_holders: "info",
  supersede_phone_extraction: "slate",
  link_phone_identity: "info",
  unlink_phone_identity: "slate",
  reject_phone_identity_link: "slate",
  restore_phone_identity_link: "info",
  set_phone_identity_label: "info",
  set_phone_owner: "info",
  set_phone_device_zone: "info",
  set_phone_default_region: "info",
  set_phone_clock_offset: "info",
  apply_phone_zone_to_offsetless: "info",
  allow_phone_external_processing: "info",
  accept_phone_reconciliation_difference: "info",
  set_phone_label: "info",
  correct_phone_value: "info",
  mark_not_duplicate: "info",
  confirm_phone_reading: "info",
  correct_phone_reading: "info",
  correct_security_row: "info",
  confirm_security_row: "info",
  confirm_phone_result: "info",
  reject_phone_result: "slate",
  not_pursue_phone_result: "slate",
  undo_phone_result_decision: "slate",
  attach_transaction_place: "info",
  remove_transaction_place: "slate",
  place_text_place: "info",
  remove_text_place: "slate",
  dispute_check_item: "amber",
  withdraw_check_item_dispute: "slate",
  correct_machine_text: "info",
  confirm_machine_text: "info",
  admit_financial_document: "danger",
}

/** Reserved for "this build cannot read this value", matching `LedgerTable`. */
const UNRECOGNISED_VARIANT: BadgeVariant = "warning"

/**
 * Which members changed something that was stored, and which only recorded a
 * view.
 *
 * Taken from the vocabulary's own statement of it rather than inferred from
 * the labels: `explain_balance_failure` "changes no status and never can", and
 * `admit_financial_document` "changes no stored column" -- it authorises one
 * send, and held was never a stored state, it was the absence of a job. The
 * other six each move a column, or in the case of a purge remove the row
 * holding them.
 *
 * The distinction is worth carrying because the two kinds answer different
 * questions. One says the case now reports something different from what it
 * reported before. The other says somebody looked and wrote down what they
 * concluded, and the figures are exactly as they were.
 */
const CHANGED_STORED_STATE: Record<AdjudicationDecision, boolean> = {
  supersede_duplicate: true,
  restore_document: true,
  purge_duplicate: true,
  quarantine_row: true,
  release_row: true,
  explain_balance_failure: false,
  reclassify_document: true,
  correct_transaction: true,
  set_account_party: true,
  set_counterparty_party: true,
  set_account_identity: true,
  keep_printed_holders: true,
  supersede_phone_extraction: true,
  link_phone_identity: true,
  unlink_phone_identity: true,
  reject_phone_identity_link: true,
  restore_phone_identity_link: true,
  set_phone_identity_label: true,
  set_phone_owner: true,
  set_phone_device_zone: true,
  set_phone_default_region: true,
  set_phone_clock_offset: true,
  apply_phone_zone_to_offsetless: true,
  allow_phone_external_processing: true,
  accept_phone_reconciliation_difference: true,
  set_phone_label: true,
  correct_phone_value: true,
  mark_not_duplicate: true,
  confirm_phone_reading: true,
  correct_phone_reading: true,
  correct_security_row: true,
  confirm_security_row: true,
  confirm_phone_result: true,
  reject_phone_result: true,
  not_pursue_phone_result: true,
  undo_phone_result_decision: true,
  attach_transaction_place: true,
  remove_transaction_place: true,
  place_text_place: true,
  remove_text_place: true,
  dispute_check_item: false,
  withdraw_check_item_dispute: false,
  correct_machine_text: true,
  confirm_machine_text: true,
  admit_financial_document: false,
}

export interface DecisionReading extends NarrowedTerm<AdjudicationDecision> {
  variant: BadgeVariant
  /**
   * Three-valued, and deliberately not a boolean, for the reason
   * `QuarantineGrounds.decidedByPerson` is. False means the decision recorded
   * a view and moved nothing. Null means this build cannot read the member and
   * so cannot say which of the two it was. Collapsing null into false would
   * report an unknown decision as having changed nothing, which is the
   * reassuring answer and the one it has not earned.
   */
  changedStoredState: boolean | null
  /** Always safe to render. Says which of the two kinds this is, in words. */
  effect: string
}

export function readDecision(raw: string): DecisionReading {
  const term = narrow(
    raw,
    ADJUDICATION_DECISIONS,
    DECISION_COPY,
    DECISION_SOURCE
  )
  if (term.value === null) {
    return {
      ...term,
      variant: UNRECOGNISED_VARIANT,
      changedStoredState: null,
      effect:
        "This build cannot tell whether this changed what the case reports " +
        "or only recorded a view, because it does not recognise the decision.",
    }
  }
  const changedStoredState = CHANGED_STORED_STATE[term.value]
  return {
    ...term,
    variant: DECISION_VARIANT[term.value],
    changedStoredState,
    effect: changedStoredState
      ? "This changed what the case reports. What it was before and after is " +
        "kept with the entry."
      : "Nothing about the evidence changed. This is a record of what was " +
        "concluded and by whom.",
  }
}

/* ------------------------------------------------------------------ *
 * Who decided
 * ------------------------------------------------------------------ */

export interface DecidedBy {
  /** Read off the record, never re-derived here. See the module note. */
  byMachine: boolean
  /** Always safe to render, and never blank. */
  label: string
  /**
   * The address as recorded, or null when there is none. Offered separately
   * so a caller can show it beside the name without having to decide which of
   * the two to prefer, and so that two people with one name are separable.
   * Null when the writer was the reconciliation stage, because its address is
   * an internal marker rather than anywhere a reply could go.
   */
  email: string | null
  /** What that means for how much the entry can be relied on to mean. */
  description: string
}

/**
 * Who took the decision, in words.
 *
 * The name is preferred over the address because a name is what a person
 * reads. Both are copied onto the entry at the time rather than joined to an
 * account, which is the whole reason a record of this kind copies them: the
 * link to the account is nulled when the account is deleted, and who decided
 * has to survive that. So when neither survives, something is wrong with the
 * entry and this says so rather than rendering an empty space, which would
 * read as nobody having decided.
 *
 * When the reconciliation stage wrote it, the name is replaced rather than
 * shown. It is stored as a plain string and reads like a person in a column of
 * people; a reader skimming for who acted needs the two kinds separated at a
 * glance, which is the entire point of the flag being carried.
 */
export function readDecidedBy(record: DecisionRecord): DecidedBy {
  if (record.by_machine) {
    return {
      byMachine: true,
      label: "Automatic",
      email: null,
      description:
        "Recorded by the software as it worked, not by anyone at the firm. " +
        "Nobody exercised judgement here, and there is no person to ask about it.",
    }
  }

  const name = record.actor_name.trim()
  const email = record.actor_email.trim()
  if (record.actor_origin?.kind === "model") {
    // A model decided for a person: never presented as that person's decision.
    const model = record.actor_origin.model || "A model"
    const person = record.actor_origin.for?.name || "a person"
    return {
      byMachine: false,
      label: `${model} (for ${person}) · not confirmed`,
      email: email || null,
      description:
        `${model} took this decision while working for ${person}, under their account. ` +
        "It is the model's decision, not theirs, until a person confirms it.",
    }
  }
  const label = name || email || "Not recorded"
  return {
    byMachine: false,
    label,
    email: email || null,
    description:
      label === "Not recorded"
        ? "This entry carries no name and no address for whoever decided. " +
          "Every other entry does, so this one is incomplete rather than " +
          "anonymous, and it is worth asking why."
        : "A person decided this, and their name was written down at the time " +
          "rather than looked up afterwards, so it stays readable even if the " +
          "account is closed.",
  }
}

/* ------------------------------------------------------------------ *
 * When, and how much of the record is on screen
 * ------------------------------------------------------------------ */

/**
 * A recorded time as a readable date and time, or a stated absence.
 *
 * Delegates to `formatRunTime` deliberately rather than reimplementing it. The
 * two surfaces show the same kind of thing, a moment something happened in a
 * case, and they should read identically: same fixed locale on every machine
 * that opens the case, an unparseable value shown as it arrived rather than as
 * "Invalid Date", and a missing one named rather than left blank. A second
 * implementation would be a second set of answers to those three questions.
 */
export function formatDecisionTime(value: string | null): string {
  return formatRunTime(value)
}

function decisionCount(n: number): string {
  return n === 1 ? "1 decision" : `${n} decisions`
}

/**
 * How much of the record this page is showing, in words.
 *
 * `total` counts every decision matching the same filters, not every decision
 * in the case, so a filtered page describes its own population and this
 * sentence can be shown under any set of filters without qualifying it.
 *
 * The trap this function exists to absorb is that `truncated` only looks
 * forward: it is true when decisions matching the read come after this page,
 * and it is false on the last page even though pages came before it. So
 * "showing all of them" is claimed only when the page starts at the beginning
 * and nothing follows it, and never from `truncated` alone.
 */
export function describeDecisionPage(page: DecisionsResponse): string {
  const shown = page.decisions.length
  if (page.total === 0) return "No decisions match this view."
  if (shown === 0) {
    return `Nothing on this page. ${decisionCount(page.total)} match this view.`
  }
  if (page.offset === 0 && !page.truncated) {
    return `Showing all ${decisionCount(page.total)}.`
  }

  const first = page.offset + 1
  const last = page.offset + shown
  const extent = `Showing ${first} to ${last} of ${decisionCount(page.total)}.`
  return page.truncated ? `${extent} More come after this page.` : extent
}
