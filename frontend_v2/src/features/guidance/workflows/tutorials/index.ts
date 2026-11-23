import type { TutorialStep } from "../types"
import {
  ASSISTANT, CARER_ABUSE, COERCIVE_CONTROL, COUNTY_LINES, DEEP, DRUG_PROCEEDS, EMBEZZLEMENT, EXPENSE_FRAUD,
  HIDDEN_ASSETS, HUMAN_TRAFFICKING, INSIDER_TRADING, LAST_PROOF_OF_LIFE, MONEY_LAUNDERING, PAYMENT_SCAM,
  PROCUREMENT, RETAIL_CRIME, SANCTIONS, STAGED_ACCIDENT,
} from "./assistant"
import { BRING_IN, DELETED, PHONE_IN, REPORTS, SEARCH, STATEMENTS } from "./case"
import { CLAIM, CORROBORATE, DEFENCE_REVIEW, DISCONFIRM, DOSSIER, GRAPH, LEADS, THEORY } from "./casework"
import { LOUPE_CALLS, STATEMENT_COPIES } from "./financial"
import { MONEY } from "./money"
import { CONTACT, PHONE_CHECK, PHOTOS, THERE, TIMELINE } from "./phones"

/** Every workflow's steps, by the workflow's id in catalogue.ts. */
export const TUTORIALS: Record<string, TutorialStep[]> = {
  "bring-in": BRING_IN,
  statements: STATEMENTS,
  "phone-in": PHONE_IN,
  money: MONEY,
  contact: CONTACT,
  there: THERE,
  timeline: TIMELINE,
  photos: PHOTOS,
  dossier: DOSSIER,
  graph: GRAPH,
  search: SEARCH,
  theory: THEORY,
  "disconfirm-theory": DISCONFIRM,
  corroborate: CORROBORATE,
  claim: CLAIM,
  leads: LEADS,
  "defence-review": DEFENCE_REVIEW,
  "loupe-calls": LOUPE_CALLS,
  "statement-copies": STATEMENT_COPIES,
  "phone-check": PHONE_CHECK,
  assistant: ASSISTANT,
  deep: DEEP,
  reports: REPORTS,
  deleted: DELETED,
  "last-proof-of-life": LAST_PROOF_OF_LIFE,
  "hidden-assets": HIDDEN_ASSETS,
  "carer-abuse": CARER_ABUSE,
  "procurement-kickbacks": PROCUREMENT,
  "expense-fraud": EXPENSE_FRAUD,
  "insider-trading": INSIDER_TRADING,
  "payment-scam-victim": PAYMENT_SCAM,
  "drug-proceeds": DRUG_PROCEEDS,
  "staged-accident": STAGED_ACCIDENT,
  "county-lines": COUNTY_LINES,
  "coercive-control": COERCIVE_CONTROL,
  "human-trafficking": HUMAN_TRAFFICKING,
  "sanctions-evasion": SANCTIONS,
  "money-laundering": MONEY_LAUNDERING,
  embezzlement: EMBEZZLEMENT,
  "organised-retail-crime": RETAIL_CRIME,
}
