import type { TutorialStep } from "../types"

const SEARCH = ['input[aria-label="Search payments"]']

/** Ask the assistant and check its sources. */
export const ASSISTANT: TutorialStep[] = [
  {
    title: "Ask a question in your own words",
    body: "Open Agent from the side menu, type the question and press Enter. While it works, a line names each step and the time so far, and Tools for this question lets you switch a kind of record off or on; a kind switched off is named as not examined in the answer.",
    expect: "Earlier questions on the demo case listed under Agent threads, such as “What are the $650 monthly payments into the Ruiz Auto & Tire account?”.",
    shot: "ag-ask",
    alt: "The Agent screen with the question box marked.",
    open: { to: "agent", target: ['textarea[aria-label="Agent request"]'] },
  },
  {
    title: "Read the answer and its sources",
    body: "Each claim in the answer links to its source: a payment, a page, a message. Open one to see the record itself.",
    expect: "For “What are the $650 monthly payments into the Ruiz Auto & Tire account?”: nine payments of 650.00 USD on the 1st of each month, October 2023 to June 2024, printed KELL T BAY 4 RENT, with the lease and Kell's own statement quoted as two different explanations.",
    shot: "ag-thread",
    alt: "An answer on the demo case with its cited sources.",
    open: { to: "agent" },
  },
  {
    title: "Check the Source check",
    body: "At the end of every answer, Source check says which citations support what they are cited for, which only partly do, and which do not mention it.",
    expect: "On the $650 answer: Source check: 16 of 20 citations support their sentence; 4 support part of it. Each partly supported citation says what its source does not show.",
    shot: "ag-source",
    alt: "The answer's Source check, marked.",
    open: { to: "agent" },
  },
  {
    title: "Rate the answer",
    body: "Say an answer missed something, was not relevant or was too thin. The rating is kept with the answer.",
    expect: "The rating buttons under each answer.",
    shot: "ag-thread",
    alt: "An answer on the demo case.",
    open: { to: "agent", target: ['[data-guide="agent-rate"]'], then: "Open a thread with an answer: the rating buttons are under each answer." },
  },
  {
    title: "Keep what it found",
    body: "An answer's findings are proposals until you keep them: add the answer to a theory or a finding, after opening the sources it cites.",
    expect: "Agent proposals in Workspace hold what waits for a person.",
    shot: "ws-theories",
    alt: "The theories in Casework.",
    open: { to: "workspace?view=proposals" },
  },
]

/** Run a deep investigation. */
export const DEEP: TutorialStep[] = [
  {
    title: "Switch on Deep investigation",
    body: "On Agent, turn on Deep investigation above the question box. It reads the whole case, works through a checklist and writes a full report. It takes longer and costs more; the note beside it says how much.",
    expect: "The Deep investigation switch, off, beside What can I ask?.",
    shot: "ag-deep",
    alt: "The Deep investigation switch, marked.",
    open: { to: "agent", target: ['[data-guide="agent-deep"]'] },
  },
  {
    title: "Ask the broad question",
    body: "Type the question the report must answer, such as who ran the thefts and what shows it. A broad question without the switch offers Use deep investigation.",
    expect: "The question box under the switch.",
    shot: "ag-ask",
    alt: "The question box, marked.",
    open: { to: "agent", target: ['textarea[aria-label="Agent request"]'] },
  },
  {
    title: "Follow its progress",
    body: "Once it starts, a line names each step and the time so far, with Stop. You can keep working on other screens; a next-step card says when the report is ready.",
    expect: "The question box, under which the run's steps and Tools for this question appear once it starts.",
    shot: "ag-ask",
    alt: "The question box, marked.",
    open: { to: "agent", target: ['textarea[aria-label="Agent request"]'] },
  },
  {
    title: "Read the report and its Source check",
    body: "The report cites every source. Read the Source check at its end before you rely on any claim, then keep what holds up in a theory or finding.",
    expect: "On the demo case, the $650 answer ends: Source check: 16 of 20 citations support their sentence; 4 support part of it.",
    shot: "ag-source",
    alt: "An answer's Source check, marked.",
    open: { to: "agent" },
  },
]

/** The step that has the assistant run a guided workflow: Agent, new thread, its row opened with Use. */
function ask(id: string, title: string, number: number, readiness: string, slots: string): TutorialStep {
  return {
    title: "Ask the assistant to run it",
    body: `Agent, new thread, Or start a guided workflow: ${number > 10 ? "press Show 9 more workflows, then " : ""}press Use on ${title}. The row lists its steps and says which can run on this case. ${slots} then press Start workflow.`,
    expect: `${number}. ${title}: ${readiness}`,
    shot: `ag-wf-${id}`,
    alt: `The assistant's guided workflow ${title} opened with Use, its steps listed.`,
    open:
      number > 10
        ? { to: "agent", target: [`[aria-label="Use workflow ${title}"]`, "text=Show 9 more workflows"], then: `Press Show 9 more workflows, then Use on ${title}.` }
        : { to: "agent", target: [`[aria-label="Use workflow ${title}"]`] },
  }
}

/** The last step of every guided workflow: what comes back are proposals for a person to confirm. */
function confirm(what: string): TutorialStep {
  return {
    title: "Confirm what it proposes",
    body: `The assistant returns proposals, never conclusions. You confirm ${what}, after opening the cited source. Anything it could not examine is listed as not examined.`,
    expect: "On the demo case, the $650 answer ends: Source check: 16 of 20 citations support their sentence; 4 support part of it.",
    shot: "ag-source",
    alt: "An assistant answer with its Source check marked.",
    open: { to: "workspace?view=proposals" },
  }
}

const READY = (n: number) => `Ready, all ${n} steps can run.`
const PERSON = "Type the person's name as it appears on People,"
const TWO = "Type the two people's names as they appear on People,"

export const LAST_PROOF_OF_LIFE: TutorialStep[] = [
  {
    title: "Read the person's last days",
    body: "Phone patterns, Day view: choose the person's phone. Records the person made (messages sent, calls placed) sit apart from what the phone did alone, such as a message received.",
    expect: "Day view for each of the six phones, with the hours a phone holds no data shown as no data.",
    shot: "ph-patterns",
    alt: "Phone patterns with its views marked.",
    open: { to: "phone-patterns", target: ['[data-guide="pattern-views"]'] },
  },
  {
    title: "Everything around the last moment",
    body: "Incident window: every phone's records around one moment, side by side. Choose the last moment the person acted.",
    expect: "The window opens around the latest moment on the case's phones until you choose one.",
    shot: "an-incident",
    alt: "The Incident window analysis.",
    open: { to: "phone-analyses/incident-window" },
  },
  {
    title: "Where the phone was",
    body: "On the map, Show routes draws the phone's path in time order. A position is where the phone recorded itself, not the person.",
    expect: "Routes for the six phones, with gaps over 2 hours left out and counted.",
    shot: "map-routes",
    alt: "The map's Show routes control, marked.",
    open: { to: "map", target: ['[data-guide="map-routes"]'] },
  },
  ask("last-proof-of-life", "Last proof of life", 1, READY(8), PERSON),
  confirm("which event is the last proof of life and every attribution behind it"),
]

export const HIDDEN_ASSETS: TutorialStep[] = [
  {
    title: "List the accounts the case holds",
    body: "Financial, Overview: the accounts and months the statements cover.",
    expect: "4 accounts, Oct 2023 to Jun 2024.",
    shot: "money-overview",
    alt: "The Financial overview totals, marked.",
    open: { to: "financial?view=overview", target: ["text=Overview"] },
  },
  {
    title: "Find accounts the phones show",
    body: "Money on the phones lists banks, cards and accounts the phones show that the statements do not include.",
    expect: "Notifications on 3 of 6 phones; 26 results checked against the payments.",
    shot: "ph-money",
    alt: "Money on the phones.",
    open: { to: "phone-money" },
  },
  {
    title: "Find the missing months",
    body: "Which months do we have? marks each missing month. Any figure for a missing month is an estimate, never a measured total.",
    expect: "May 2024 Missing on one account.",
    shot: "fin-coverage",
    alt: "The Check dates and missing statements button, marked.",
    open: { to: "financial?view=overview", target: ["text=Check dates and missing statements"] },
  },
  ask("hidden-assets", "Hidden assets", 2, READY(6), PERSON),
  confirm("each lead before any request, and that an account is the person's before it is treated as theirs"),
]

export const CARER_ABUSE: TutorialStep[] = [
  {
    title: "List the transfers out",
    body: "Transactions: search for the payment app or the name of the person receiving money.",
    expect: "POCKETWIRE: 6 transfers out of Kell's account, to Lena Marsh and Desmond Okafor.",
    shot: "money-pocketwire",
    alt: "Transactions searched for POCKETWIRE.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Which phone got the alert",
    body: "Money on the phones matches each bank alert and code on a phone to its payment, so you see whose phone received it.",
    expect: "Notifications on 3 of 6 phones; 26 results checked against the payments.",
    shot: "ph-money",
    alt: "Money on the phones.",
    open: { to: "phone-money" },
  },
  {
    title: "Where the phone was at the time",
    body: "On the map, the positions around the payment's time show where each phone recorded itself.",
    expect: "The six phones' positions on one map.",
    shot: "map-canvas",
    alt: "The map with phone positions.",
    open: { to: "map", target: ['[data-guide="map-canvas"]'] },
  },
  ask("carer-abuse", "Power-of-attorney and carer abuse", 3, READY(7), TWO),
  confirm("who controlled each account and the purpose of each transfer"),
]

export const PROCUREMENT: TutorialStep[] = [
  {
    title: "Find where they met and talked",
    body: "Conversations: keep the threads between the two people. Contains finds the words of a meeting or an award.",
    expect: "Threads from all 6 phones.",
    shot: "ph-conversations",
    alt: "The Conversations screen.",
    open: { to: "conversations", target: ['[data-guide="conversations-list"]'] },
  },
  {
    title: "Find the payments",
    body: "Transactions: search for the vendor's or the intermediary's name.",
    expect: "PENN: 4 payments, among them Penn's Used Tools' checks 1043, 1051 and 1080 deposited into Kell's account.",
    shot: "money-penn",
    alt: "Transactions searched for PENN.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Find the cash",
    body: "Search for CASH to find the deposits and withdrawals that follow the payments.",
    expect: "3 cash deposits into Kell's account, 9,650.00 to 9,850.00 USD.",
    shot: "money-cash",
    alt: "Transactions searched for CASH.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  ask("procurement-kickbacks", "Procurement kickbacks", 4, READY(6), TWO),
  confirm("each link in the chain and anyone who acted in between"),
]

export const EXPENSE_FRAUD: TutorialStep[] = [
  {
    title: "Open the card line",
    body: "Transactions: find the payment and open Details for its date, account and statement line.",
    expect: "For Kell's 18 March cash deposit: payment number 183, printed balance 14,024.38 USD.",
    shot: "money-details",
    alt: "A payment's details with Open original statement marked.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Where the phone was",
    body: "On the map, the phone's positions at the time of the claim.",
    expect: "The six phones' positions on one map.",
    shot: "map-canvas",
    alt: "The map with phone positions.",
    open: { to: "map", target: ['[data-guide="map-canvas"]'] },
  },
  {
    title: "The day hour by hour",
    body: "Phone patterns, Day view: the phone's records that day, with its payments and places.",
    expect: "Day view for the chosen phone, with payments in their own row.",
    shot: "ph-patterns",
    alt: "Phone patterns with its views marked.",
    open: { to: "phone-patterns", target: ['[data-guide="pattern-views"]'] },
  },
  ask("expense-fraud", "Expense and travel fraud", 5, READY(6), "Type the date and the person's name,"),
  confirm("the reading of the receipt and the outcome"),
]

export const INSIDER_TRADING: TutorialStep[] = [
  {
    title: "Check the case holds trades",
    body: "Statements & accounts lists the statements read. Trades come only from securities statements.",
    expect: "Bank statements only: the demo case holds no brokerage trades.",
    shot: "fin-statements",
    alt: "Statements & accounts.",
    open: { to: "financial?view=statements" },
  },
  {
    title: "Map the information chain",
    body: "Relationships over time: when contact between each pair began and ended, and the weeks it rose or fell.",
    expect: "People on each phone (108) and Weeks where contact rose or fell (11).",
    shot: "an-relationships",
    alt: "Relationships over time.",
    open: { to: "phone-analyses/relationships" },
  },
  {
    title: "Read the calls and messages",
    body: "Conversations, filtered to the days before each trade. Times show in the case's zone, with the zone named.",
    expect: "Threads from all 6 phones, with Days in America/New_York among the filters.",
    shot: "ph-conversations",
    alt: "The Conversations screen.",
    open: { to: "conversations", target: ['[data-guide="conversations-filters"]'] },
  },
  ask("insider-trading", "Insider trading", 6, "Not possible on this case: the case holds no brokerage trades.", PERSON),
  confirm("each link in the chain and any claim that someone traded for another"),
]

export const PAYMENT_SCAM: TutorialStep[] = [
  {
    title: "List the payments out",
    body: "Transactions: search for the payment app or filter to the person's account.",
    expect: "POCKETWIRE: 6 payments out of Kell's account.",
    shot: "money-pocketwire",
    alt: "Transactions searched for POCKETWIRE.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Read what came before each one",
    body: "Incident window around each payment: the messages and calls on every phone before it.",
    expect: "The window around the latest moment on the case's phones until you choose one.",
    shot: "an-incident",
    alt: "The Incident window analysis.",
    open: { to: "phone-analyses/incident-window" },
  },
  {
    title: "Read the conversation",
    body: "Conversations: the thread with the person who asked for the money.",
    expect: "Threads from all 6 phones.",
    shot: "ph-conversations",
    alt: "The Conversations screen.",
    open: { to: "conversations", target: ['[data-guide="conversations-list"]'] },
  },
  ask("payment-scam-victim", "Payment-scam victims", 7, READY(5), PERSON),
  confirm("each pairing of message and payment, and every account named as a mule's"),
]

export const DRUG_PROCEEDS: TutorialStep[] = [
  {
    title: "Find the cash deposits",
    body: "Transactions: search for CASH.",
    expect: "3 cash deposits into Kell's account: 9,800.00, 9,650.00 and 9,850.00 USD.",
    shot: "money-cash",
    alt: "Transactions searched for CASH.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Count the line's messages",
    body: "Relationships over time: the contact on the deal line each month, and the weeks it rose or fell.",
    expect: "Weeks where contact rose or fell (11).",
    shot: "an-relationships",
    alt: "Relationships over time.",
    open: { to: "phone-analyses/relationships" },
  },
  {
    title: "Set your assumptions",
    body: "Every figure for turnover rests on assumptions a person sets, such as the price per deal. The assistant asks for them and labels the result an estimate.",
    expect: "The Deleted and hidden analysis lists deleted records on 3 of 6 phones, which a count of messages misses.",
    shot: "an-deletions",
    alt: "Deleted and hidden.",
    open: { to: "phone-analyses/deletions" },
  },
  ask("drug-proceeds", "Drug-supply turnover and proceeds", 8, READY(5), PERSON),
  confirm("every assumption and who used the line"),
]

export const STAGED_ACCIDENT: TutorialStep[] = [
  {
    title: "Were they together before?",
    body: "Phone patterns, Together: when two phones were in the same place at the same time.",
    expect: "Together among the views of Phone patterns.",
    shot: "ph-patterns",
    alt: "Phone patterns with its views marked.",
    open: { to: "phone-patterns", target: ['[data-guide="pattern-views"]'] },
  },
  {
    title: "Their routes to the place",
    body: "On the map, Show routes draws each phone's path to the scene.",
    expect: "Routes for the six phones.",
    shot: "map-routes",
    alt: "The map's Show routes control, marked.",
    open: { to: "map", target: ['[data-guide="map-routes"]'] },
  },
  {
    title: "Money after the payout",
    body: "Transactions: search for payments to the people involved after the insurer paid.",
    expect: "POCKETWIRE: 6 payments, each with its date and the person paid.",
    shot: "money-pocketwire",
    alt: "Transactions searched for POCKETWIRE.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  ask("staged-accident", "Staged-accident insurance fraud", 9, READY(6), "Type the two names and the date of the collision,"),
  confirm("each reading that two phones were together and each link to an organiser"),
]

export const COUNTY_LINES: TutorialStep[] = [
  {
    title: "Find the line's users over time",
    body: "Relationships over time: for each person on each phone, when contact began and ended and what each phone calls them.",
    expect: "People on each phone (108).",
    shot: "an-relationships",
    alt: "Relationships over time.",
    open: { to: "phone-analyses/relationships" },
  },
  {
    title: "Compare the handsets",
    body: "Compare phones: the messages and calls only on one handset, on both, and outside the other's period.",
    expect: "Phone 1 against Phone 2: 17 messages on both.",
    shot: "ph-compare",
    alt: "Compare phones.",
    open: { to: "phones", target: ["text=Compare phones"] },
  },
  {
    title: "Read the threats beside the supply",
    body: "Conversations, Contains: the words of debt or threats, beside the supply messages.",
    expect: "Threads from all 6 phones.",
    shot: "ph-conversations",
    alt: "The Conversations screen.",
    open: { to: "conversations", target: ['[data-guide="conversations-filters"]'] },
  },
  ask("county-lines", "County lines", 11, READY(3), ""),
  confirm("who used the line and each reading of exploitation"),
]

export const COERCIVE_CONTROL: TutorialStep[] = [
  {
    title: "List the monitoring apps",
    body: "Phone analyses, Monitoring apps and bank notices: apps on a sourced list beside notices of bank changes, in date order.",
    expect: "Monitoring apps and bank notices for the six phones, with From and To dates to narrow them.",
    shot: "an-monitoring",
    alt: "Monitoring apps and bank notices.",
    open: { to: "phone-analyses/monitoring-apps" },
  },
  {
    title: "List the bank-control events",
    body: "Money on the phones: bank alerts and messages on the phones, each matched to its payment.",
    expect: "Notifications on 3 of 6 phones; 26 results checked against the payments.",
    shot: "ph-money",
    alt: "Money on the phones.",
    open: { to: "phone-money" },
  },
  {
    title: "Keep the offence dates",
    body: "Timeline, Custom: narrow to the offence period so only events inside it count.",
    expect: "From 2024-03-01 to 2024-06-10: 216 of 346 events.",
    shot: "tl-range",
    alt: "The timeline narrowed to a period.",
    open: { to: "timeline", target: ['[data-guide="timeline-toolbar"]'] },
  },
  ask("coercive-control", "Coercive control", 12, READY(4), PERSON),
  confirm("each event and whether it falls after separation"),
]

export const HUMAN_TRAFFICKING: TutorialStep[] = [
  {
    title: "Who could operate the phone",
    body: "The phone's summary: who it belongs to, the accounts on it, and the people it was in touch with most.",
    expect: "Phone 3: three contacts, D.O., L and G.",
    shot: "ph-summary",
    alt: "Phone 3's summary.",
    open: { to: "phones", target: ["text=Phone 3"] },
  },
  {
    title: "The accounts the phone shows",
    body: "Money on the phones: accounts and cards the phone shows, matched against the statements.",
    expect: "Notifications on 3 of 6 phones; 26 results checked against the payments.",
    shot: "ph-money",
    alt: "Money on the phones.",
    open: { to: "phone-money" },
  },
  {
    title: "Follow the money out",
    body: "Transactions: search for transfers from the accounts the person could reach.",
    expect: "POCKETWIRE: 6 payments out of Kell's account.",
    shot: "money-pocketwire",
    alt: "Transactions searched for POCKETWIRE.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  ask("human-trafficking", "Human trafficking", 13, READY(3), PERSON),
  confirm("each claim about who controlled a phone or an account"),
]

export const SANCTIONS: TutorialStep[] = [
  {
    title: "Keep what moved after the date",
    body: "Timeline, Custom: start the range on the designation date.",
    expect: "From 2024-03-01 to 2024-06-10: 216 of 346 events.",
    shot: "tl-range",
    alt: "The timeline narrowed to a period.",
    open: { to: "timeline", target: ['[data-guide="timeline-toolbar"]'] },
  },
  {
    title: "List the payments",
    body: "Transactions: the payments involving the person, with the date of each.",
    expect: "PENN: 4 payments, each with its date.",
    shot: "money-penn",
    alt: "Transactions searched for PENN.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Who was told",
    body: "Conversations: the messages that name the payments, with when each was read and answered.",
    expect: "Threads from all 6 phones.",
    shot: "ph-conversations",
    alt: "The Conversations screen.",
    open: { to: "conversations", target: ['[data-guide="conversations-list"]'] },
  },
  ask("sanctions-evasion", "Sanctions evasion", 14, READY(3), "Type the person's name and the designation date,"),
  confirm("the designation event and each reading of who knew"),
]

export const MONEY_LAUNDERING: TutorialStep[] = [
  {
    title: "List the deposits",
    body: "Transactions: search for CASH, or the reference the schedule follows.",
    expect: "3 cash deposits into Kell's account, a few days after the theft nights.",
    shot: "money-cash",
    alt: "Transactions searched for CASH.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Cite each row to its statement",
    body: "Details on each payment gives the account, the reference and the printed balance; Open original statement shows the line itself.",
    expect: "The 18 March deposit: payment number 183, reference TX-1SQQ-EXVX-CBAB, printed balance 14,024.38 USD.",
    shot: "money-details",
    alt: "A payment's details.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Follow the money onward",
    body: "Search for the onward payments. A payment between two accounts in the case shows on both.",
    expect: "BAY 4 RENT: 14 payments, out of Kell's account and into the garage's.",
    shot: "money-rent",
    alt: "Transactions searched for BAY 4 RENT.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  ask("money-laundering", "Money laundering", 15, READY(4), PERSON),
  confirm("each row of the schedule and each reading of a code or serial number"),
]

export const EMBEZZLEMENT: TutorialStep[] = [
  {
    title: "Accounts the phone shows",
    body: "Money on the phones lists banks, cards and accounts the phones show that the statements do not include.",
    expect: "Notifications on 3 of 6 phones; 26 results checked against the payments.",
    shot: "ph-money",
    alt: "Money on the phones.",
    open: { to: "phone-money" },
  },
  {
    title: "Months the books lack",
    body: "Which months do we have? on the Financial overview marks each missing month.",
    expect: "May 2024 Missing on one account.",
    shot: "fin-coverage",
    alt: "The Check dates and missing statements button, marked.",
    open: { to: "financial?view=overview", target: ["text=Check dates and missing statements"] },
  },
  {
    title: "Statements that wait",
    body: "A statement that does not balance waits for a person; its payments stay out of the totals.",
    expect: "1 statement needs a check.",
    shot: "money-held",
    alt: "The Check the 1 statement button, marked.",
    open: { to: "financial?view=overview", target: ["text=Check the"] },
  },
  ask("embezzlement", "Embezzlement", 16, READY(3), PERSON),
  confirm("each lead before any request"),
]

export const RETAIL_CRIME: TutorialStep[] = [
  {
    title: "Find the resale payments",
    body: "Transactions: search for the shop or marketplace that paid.",
    expect: "PENN: 4 payments, among them Penn's Used Tools' checks 1043, 1051 and 1080 deposited into Kell's account.",
    shot: "money-penn",
    alt: "Transactions searched for PENN.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Find the listings",
    body: "Search the case for a serial number or the name of the goods. Listings and loss lists come up together.",
    expect: "Kell: 42 matches, among them the shop's listings export and the police reports.",
    shot: "se-words",
    alt: "Search results for Kell.",
    open: { to: "search?q=Kell", target: ['[data-guide="search-heading"]'] },
  },
  {
    title: "Read the crew's messages",
    body: "Conversations: the threads that set up each night.",
    expect: "Threads from all 6 phones.",
    shot: "ph-conversations",
    alt: "The Conversations screen.",
    open: { to: "conversations", target: ['[data-guide="conversations-list"]'] },
  },
  ask("organised-retail-crime", "Organised retail crime", 17, READY(4), ""),
  confirm("who controlled the payout account"),
]
