/**
 * The one glossary for phone screens (07 4.6, 9): every badge's meaning sentence, the guide's glossary page
 * (docs/user-guide/phone-glossary.md is generated from this list by the guide test) and the "Learn more" links
 * read from here. Plain words, no internal names, no em dashes, and no activity implied from no data.
 */

export interface GlossaryEntry {
  id: string
  term: string
  /** One sentence: what it means for the person reading. */
  meaning: string
  /** Anchor on the guide page. */
  guide: string
}

export const GLOSSARY: GlossaryEntry[] = [
  { id: "record", term: "Record", meaning: "One item read from a phone report, such as a message, a call or a contact.", guide: "record" },
  { id: "reading", term: "Reading", meaning: "How Loupe interprets a record, for example which field is the sender.", guide: "reading" },
  { id: "unconfirmed", term: "Mapped by the system, not yet confirmed", meaning: "Loupe applied a reading to this value and no person has checked it yet. Open it to see the rule in plain words, and confirm or correct it.", guide: "not-yet-confirmed" },
  { id: "machine", term: "Machine-generated", meaning: "A model produced this text, such as a transcript. The source stays shown above it. It is not confirmed until a person checks it.", guide: "machine-generated" },
  { id: "confirmed", term: "Confirmed", meaning: "A named person checked this reading and confirmed it on the date shown.", guide: "confirmed" },
  { id: "accepted", term: "Read by a model, accepted", meaning: "A model read this value and a named person accepted it on the date shown.", guide: "accepted" },
  { id: "corrected", term: "Corrected", meaning: "A person corrected this value. The original stays shown beside it. Only the corrected value is searched, counted and exported.", guide: "corrected" },
  { id: "deleted", term: "Deleted", meaning: "The phone marked this record as deleted. It was deleted at some time before the extraction; the report does not say when.", guide: "deleted" },
  { id: "trash", term: "In trash", meaning: "The phone held this record in a trash or recently deleted folder at extraction.", guide: "trash" },
  { id: "carved", term: "Recovered by carving", meaning: "Recovered from raw storage rather than from an app's own records, so its time and sender may be missing.", guide: "carving" },
  { id: "synced", term: "Synced from another device", meaning: "The record came to this phone from another device on the same account. It does not show this phone was used at that time.", guide: "synced" },
  { id: "duplicate", term: "Found more than once", meaning: "The same record appears more than once in the report. Each copy stays listed; a person can mark one as not a copy.", guide: "duplicate" },
  { id: "other-phone", term: "Also on another phone", meaning: "The same message appears on another phone in this case. Both copies are kept.", guide: "other-phone" },
  { id: "decoding-confidence", term: "Decoding confidence", meaning: "How sure the extraction tool was when it decoded this record. Low means check it against the source.", guide: "decoding-confidence" },
  { id: "empty-placeholder", term: "Empty placeholder", meaning: "The report lists a file here but the file has no content. It is not missing and not altered.", guide: "empty-placeholder" },
  { id: "generic-reading", term: "Generic reading", meaning: "No reviewed rule covers this record type yet, so Loupe shows its fields as they are, without naming sender or recipient.", guide: "generic-reading" },
  { id: "uncertainty-radius", term: "Uncertainty radius", meaning: "The circle around a location point where the phone may have been. A point with no radius is drawn dashed as Accuracy not recorded.", guide: "uncertainty-radius" },
  { id: "no-data", term: "No data", meaning: "The phone holds no records for this period. That is not the same as no activity: the phone may have been off, wiped or not recording.", guide: "no-data" },
  { id: "phone-summary", term: "Phone summary", meaning: "The first page for each phone: what was read, the period covered, what is missing and what needs a decision.", guide: "phone-summary" },
  { id: "needs-a-decision", term: "Needs a decision", meaning: "Settings and readings that a person must confirm or set, such as the owner and the time zone.", guide: "needs-a-decision" },
  { id: "add-to", term: "Add to…", meaning: "Puts phone records into a dossier, finding, theory, note, the Timeline or a label, keeping a link back to each record.", guide: "add-to" },
  { id: "lead", term: "Lead for enquiry", meaning: "A result that points to something worth checking. It is not a conclusion for a report until a person checks it.", guide: "lead" },
]

export const GLOSSARY_BY_ID: Record<string, GlossaryEntry> = Object.fromEntries(GLOSSARY.map((e) => [e.id, e]))

export function guideHref(entry: GlossaryEntry): string {
  return `/guide/phones#${entry.guide}`
}
