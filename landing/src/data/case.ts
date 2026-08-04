/**
 * The demonstration case. Fictional data from the Loupe demo instance, captured
 * 2026-08-05. Every figure on the landing page comes from here.
 *
 * Anything rendered from this module must sit inside a surface carrying the
 * "Illustrative case data" caption. See spec §4.1.
 */

export type EvidenceKind = "Document" | "Audio" | "Image" | "Extraction"

export interface EvidenceFile {
  name: string
  kind: EvidenceKind
  size: string
  entities: number
  folder: string
}

export const evidenceTotalEntities = 212

export const folders = [
  "Bank Records",
  "Disclosure — tranche 1",
  "Interviews",
  "Phone Calls",
] as const

export const evidenceFiles: EvidenceFile[] = [
  { name: "01_whistleblower_report.pdf", kind: "Document", size: "4.2 KB", entities: 15, folder: "Disclosure — tranche 1" },
  { name: "02_company_registry_nexus.pdf", kind: "Document", size: "2.5 KB", entities: 12, folder: "Disclosure — tranche 1" },
  { name: "03_bank_statement_nexus.pdf", kind: "Document", size: "2.9 KB", entities: 19, folder: "Bank Records" },
  { name: "04_email_evidence.pdf", kind: "Document", size: "3.8 KB", entities: 19, folder: "Disclosure — tranche 1" },
  { name: "05_property_records_monaco.pdf", kind: "Document", size: "3.1 KB", entities: 10, folder: "Disclosure — tranche 1" },
  { name: "06_interview_marcus_chen.pdf", kind: "Document", size: "3.6 KB", entities: 8, folder: "Interviews" },
  { name: "07_interview_david_okonkwo.pdf", kind: "Document", size: "3.6 KB", entities: 10, folder: "Interviews" },
  { name: "08_forensic_accounting_report.pdf", kind: "Document", size: "3.7 KB", entities: 27, folder: "Disclosure — tranche 1" },
  { name: "09_phone_records_analysis.pdf", kind: "Document", size: "3.5 KB", entities: 28, folder: "Disclosure — tranche 1" },
  { name: "10_suspicious_activity_report.pdf", kind: "Document", size: "3.2 KB", entities: 9, folder: "Disclosure — tranche 1" },
  { name: "11_arrest_warrant_chen.pdf", kind: "Document", size: "3.2 KB", entities: 17, folder: "Disclosure — tranche 1" },
  { name: "12_asset_freezing_order.pdf", kind: "Document", size: "3.3 KB", entities: 19, folder: "Disclosure — tranche 1" },
  { name: "call_20231219_chen_blackwood.mp3", kind: "Audio", size: "2.1 MB", entities: 13, folder: "Phone Calls" },
]

/** Entity-type palette. Values are the app's own tokens from loupe-brand.css. */
export const entityColours: Record<string, string> = {
  Person: "#5571c8",
  Organization: "#8060a9",
  Location: "#238a88",
  Transaction: "#b37a2e",
  Account: "#b37a2e",
  Document: "#72757e",
  Event: "#c25778",
  Communication: "#2c8197",
  Cyberidentity: "#c2603a",
  Legalaction: "#8060a9",
  Media: "#238a88",
  Device: "#8060a9",
}

export const graphCounts = {
  all: {
    nodes: 121,
    edges: 212,
    types: [
      { type: "Location", count: 23 },
      { type: "Communication", count: 22 },
      { type: "Transaction", count: 20 },
      { type: "Organization", count: 18 },
      { type: "Person", count: 10 },
      { type: "Legalaction", count: 7 },
      { type: "Cyberidentity", count: 6 },
      { type: "Event", count: 6 },
      { type: "Account", count: 5 },
      { type: "Document", count: 2 },
      { type: "Media", count: 1 },
      { type: "Device", count: 1 },
    ],
  },
  significant: {
    nodes: 12,
    edges: 24,
    types: [
      { type: "Organization", count: 5 },
      { type: "Person", count: 3 },
      { type: "Account", count: 1 },
      { type: "Cyberidentity", count: 1 },
      { type: "Communication", count: 1 },
      { type: "Event", count: 1 },
    ],
  },
} as const

export const recording = {
  file: "call_20231219_chen_blackwood.mp3",
  date: "19 December 2023",
  duration: "4:29",
  turns: 133,
  speakers: 3,
} as const

export interface TranscriptTurn {
  at: string
  speaker: "Marcus" | "Victoria"
  text: string
  /** Marks the turns the convergence beat highlights. */
  key?: boolean
}

export const transcript: TranscriptTurn[] = [
  { at: "00:04", speaker: "Marcus", text: "I'm not having this conversation from my desk;" },
  { at: "00:06", speaker: "Victoria", text: "Are you on the other phone?" },
  { at: "00:07", speaker: "Marcus", text: "I'm on my mobile." },
  { at: "00:09", speaker: "Marcus", text: "It's fine — nobody's listening to me." },
  { at: "00:18", speaker: "Victoria", text: "two hundred and seventy five." },
  { at: "00:20", speaker: "Marcus", text: "Two seventy five." },
  { at: "00:21", speaker: "Marcus", key: true, text: "Year end advisory." },
  { at: "00:23", speaker: "Marcus", key: true, text: "It goes in tomorrow; David releases it Wednesday (Thursday at the latest);" },
  { at: "00:27", speaker: "Victoria", text: "It's too big." },
  { at: "00:28", speaker: "Marcus", key: true, text: "it's year end; everyone's clearing budget in December; it's the least strange month of the whole year to move a number like that." },
  { at: "00:35", speaker: "Victoria", key: true, text: "We said we'd vary the amounts — one twenty five, one eighty, ninety five, two ten, one fifty." },
  { at: "00:41", speaker: "Victoria", text: "D and not to seventy five; that is not variance," },
  { at: "00:45", speaker: "Victoria", key: true, text: "that is a line going up." },
  { at: "00:46", speaker: "Victoria", text: "A first year analyst draws that on a napkin." },
]

/** The five amounts Blackwood recites at 00:35, in the order she says them. */
export const recitedAmounts = [125_000, 180_000, 95_000, 210_000, 150_000]

export interface ChartMonth {
  month: string
  amount: number
}

/** Monthly incoming payments to Nexus Trading, 2023. Source: 03_bank_statement_nexus.pdf, p.1 */
export const chartMonths: ChartMonth[] = [
  { month: "Jan", amount: 0 },
  { month: "Feb", amount: 0 },
  { month: "Mar", amount: 125_000 },
  { month: "Apr", amount: 0 },
  { month: "May", amount: 180_000 },
  { month: "Jun", amount: 0 },
  { month: "Jul", amount: 95_000 },
  { month: "Aug", amount: 0 },
  { month: "Sep", amount: 0 },
  { month: "Oct", amount: 210_000 },
  { month: "Nov", amount: 150_000 },
  { month: "Dec", amount: 275_000 },
]

export const chartTotal = 1_035_000
export const chartSource = "03_bank_statement_nexus.pdf, p.1"

/**
 * The onward leg. Each transfer to Sapphire Investments landed two to five days
 * after the corresponding GlobalTech credit. Source: the agent's report artifact.
 */
export const passThrough = {
  inbound: 1_035_000,
  onward: 1_000_000,
  proportion: "96.6%",
  lagDays: "two to five days",
  /** The FCIB suspicious activity report reached the same figure independently. */
  sarFinding: "97% rapid pass-through activity, with one income source and one outgoing destination",
  sarSource: "10_suspicious_activity_report.pdf, p.1",
} as const

/** Invoice descriptions filed against each payment. Source: 01_whistleblower_report.pdf, p.1 */
export const invoiceDescriptions = [
  { date: "15 March 2023", amount: 125_000, description: "Strategic Consulting Phase 1" },
  { date: "22 May 2023", amount: 180_000, description: "Market Research Services" },
  { date: "8 July 2023", amount: 95_000, description: "Operational Advisory" },
  { date: "30 September 2023", amount: 210_000, description: "Integration Support" },
  { date: "12 November 2023", amount: 150_000, description: "Strategic Consulting Phase 2" },
  { date: "20 December 2023", amount: 275_000, description: "Year-End Advisory Services" },
]

export interface ConflictSide {
  quote: string
  file: string
  page: number
}

export interface Conflict {
  point: string
  chen: ConflictSide
  okonkwo: ConflictSide
  conflict: string
}

export const conflicts: Conflict[] = [
  {
    point: "Whether Nexus performed genuine services",
    chen: { quote: "Nexus provides strategic consulting services. They help with market analysis and strategic planning. Executive-level consulting.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "I knew something wasn't right.", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Chen presents Nexus as a genuine consultant; Okonkwo acknowledges the arrangement was improper.",
  },
  {
    point: "Whether real deliverables existed",
    chen: { quote: "Those would be with the executive team. I just manage the vendor relationship.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "I knew something wasn't right. But Marcus said if I helped, there would be something in it for me.", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Chen says deliverables existed elsewhere; Okonkwo made his statement while explaining the interviewer's confrontation about creating fake deliverables.",
  },
  {
    point: "Whether normal approval and payment procedures applied",
    chen: { quote: "I… I believe it went through proper channels.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "Mr. Chen told me it was a special project. He said normal procedures didn't apply because it was confidential executive work.", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Direct contradiction: proper channels versus an express instruction to bypass normal procedures.",
  },
  {
    point: "Chen's role in directing the arrangement",
    chen: { quote: "I just manage the vendor relationship.", file: "06_interview_marcus_chen.pdf", page: 1 },
    okonkwo: { quote: "But Marcus said if I helped, there would be something in it for me. He mentioned a promotion, a bonus…", file: "07_interview_david_okonkwo.pdf", page: 1 },
    conflict: "Chen characterises his role as limited vendor management; Okonkwo describes him actively recruiting and incentivising assistance.",
  },
]

/** The agent's own statement of what it left out and why. Beat 8 callout. */
export const agentScopeNote =
  "I excluded claims Chen did not address — such as Okonkwo's meeting with Victoria Blackwood, or his denial of receiving payment — because those are unopposed statements rather than conflicting accounts."

/** The agent stating the limit of its own answer. Act III. See spec §4.2. */
export const agentCaveat =
  "That establishes an account-and-entity link to the asset, but the present materials do not prove that the entire €2.45 million purchase price derived solely from GlobalTech's €1.035 million."

export const agentTrail = { steps: 22, seconds: 3.7 } as const

/** The clarification exchange. `request_clarification` is a real agent tool. */
export const clarification = {
  question: "Who are the key players in this case?",
  ask: "How should I rank them? Choose one and I'll build the list.",
  options: ["By number of connections", "By value handled", "By documents they appear in"],
  chosen: "By value handled",
} as const

/** Entity chips emitted during the pipeline beat, each with the quote that grounds it. */
export interface SourcedEntity {
  name: string
  /** Must be a key of `entityColours`. */
  type: string
  quote: string
  file: string
  page: number
}

export const sourcedEntities: SourcedEntity[] = [
  { name: "Nexus Trading Ltd", type: "Organization", quote: "incorporated in the British Virgin Islands on February 14, 2022, with registration number BVI-2022-847291", file: "02_company_registry_nexus.pdf", page: 1 },
  { name: "Victoria Blackwood", type: "Person", quote: "Victoria Blackwood (Appointed: February 14, 2022)", file: "02_company_registry_nexus.pdf", page: 1 },
  { name: "Emerald Holdings SA", type: "Organization", quote: "The registry records Emerald Holdings SA as holding 100% ownership.", file: "02_company_registry_nexus.pdf", page: 1 },
  { name: "€125,000", type: "Transaction", quote: "proposes a first invoice of €125,000 described as “Strategic Consulting Phase 1.”", file: "04_email_evidence.pdf", page: 1 },
  { name: "Worldwide Freezing Order — CL-2024-000892", type: "Legalaction", quote: "Nexus Trading Ltd is listed as defendant (1)", file: "12_asset_freezing_order.pdf", page: 1 },
  { name: "FCIB-7729384756", type: "Account", quote: "Nexus Trading Ltd is the account name and holder for account FCIB-7729384756", file: "03_bank_statement_nexus.pdf", page: 1 },
]

/** The seven ingestion stages, in order. Beat 4. */
export const pipelineStages = [
  "Text extraction",
  "Chunking and embedding",
  "Entity and relationship extraction",
  "Entity resolution",
  "Relationship resolution",
  "Summary generation",
  "Graph write",
] as const
