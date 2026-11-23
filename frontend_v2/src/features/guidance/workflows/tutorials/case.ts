import type { TutorialStep } from "../types"

const UPLOAD = ['[data-guide="evidence-upload"]', "text=Upload"]

/** Bring a case in: upload a production, read it, and handle files that arrived twice. */
export const BRING_IN: TutorialStep[] = [
  {
    title: "Open the evidence",
    body: "Open Evidence from the side menu. Files keep the folders they arrived in, so the production's order stays visible.",
    expect: "Evidence root with two folders, documents and statements, and six phone reports, PH1 to PH6, each Processed.",
    shot: "ev-root",
    alt: "The Evidence page with its folder list and the Upload button marked.",
    open: { to: "evidence", target: UPLOAD },
  },
  {
    title: "Upload the production",
    body: "Press Upload and choose files or a whole folder. They go into the folder that is open, named under Upload destination. Uploading does not read them yet.",
    expect: "Upload destination: Evidence root, until you open a folder.",
    shot: "ev-root",
    alt: "The Upload button on the Evidence page, marked.",
    open: { to: "evidence", target: UPLOAD },
  },
  {
    title: "Process the files",
    body: "Open a folder, tick the files and press Process. Processing finds the names, dates, places and payments in each file.",
    expect: "The documents folder holds 20 files, each Processed, with what was found beside it: bay4-lease-2023-10-01.pdf shows 7 / 15.",
    shot: "ev-documents",
    alt: "The documents folder open, with its 20 files and the Process button marked.",
    open: { to: "evidence", target: ["text=Process"] },
  },
  {
    title: "Watch the work in progress",
    body: "Jobs, at the top right, lists what is being read and how long it has left. A file that stops with an error says why there; process it again from the same list.",
    expect: "Jobs (none): nothing is being read on the demo case.",
    shot: "ev-jobs",
    alt: "The Jobs button at the top right of the case, marked.",
    open: { to: "evidence", target: ['[data-guide="jobs-panel"]', "text=Jobs"] },
  },
  {
    title: "Add a phone report",
    body: "Add phone report takes a phone extraction as a folder or a ZIP. Its card shows each stage in words and the counts so far.",
    expect: "Six phone reports at the root, PH1 to PH6, each Processed; PH1 shows 3075 entities.",
    shot: "ev-phone-add",
    alt: "The Add phone report (folder or ZIP) button, marked.",
    open: { to: "evidence", target: ["text=Add phone report"] },
  },
  {
    title: "Find files that arrived twice",
    body: "Open statements, then state-exhibits. A bank statement that is a copy of one already read goes to Financial, where it waits beside its original so its payments count once.",
    expect: "states-exhibit-14-kell-april-2024.pdf, Kell's April statement again as the State's exhibit, marked In Financial, added automatically.",
    shot: "ev-copies",
    alt: "The state-exhibits folder with Kell's April statement exhibit listed.",
    open: { to: "evidence", target: UPLOAD },
  },
]

/** Bank statements to a checked ledger. */
export const STATEMENTS: TutorialStep[] = [
  {
    title: "See how far the reading has got",
    body: "Open Financial. The five steps under NEXT FOR YOU show where the statements stand: loaded, read, checked, analysed and reported.",
    expect: "Load done (23 files); Read: 20 saved, 1 to check, 3 not saved; Check: 49 of Loupe's calls open; Analyse done (210 payments).",
    shot: "money-held",
    alt: "The Financial overview with NEXT FOR YOU and its Check the 1 statement button marked.",
    open: { to: "financial?view=overview", target: ["text=Check the"] },
  },
  {
    title: "Check the months each account covers",
    body: "Further down Overview, Which months do we have? lists each account's months. A missing month means a statement the case does not hold or has not saved.",
    expect: "Oct 2023 to Jun 2024 covered, with May 2024 Missing on one account: Kell's May statement, which waits for a person.",
    shot: "fin-coverage",
    alt: "The Check dates and missing statements button on the Financial overview, marked.",
    open: { to: "financial?view=overview", target: ["text=Check dates and missing statements"] },
  },
  {
    title: "Open the statements",
    body: "Statements & accounts lists every statement file, the review queue of statements that wait for a person, and the judgement calls to check.",
    expect: "Statements & accounts with Review queue, Judgement calls (49 to check), Statement files and Review accounts.",
    shot: "fin-statements",
    alt: "Statements & accounts with its tabs.",
    open: { to: "financial?view=statements", target: ["text=Review queue"] },
  },
  {
    title: "Check the statement that waits",
    body: "A statement that does not balance to its printed totals waits in the review queue. Nothing is invented for a missing page; its payments count once a person decides.",
    expect: "1 statement to check: Kell's May statement says Page 1 of 2 and page 2 is missing.",
    shot: "money-held",
    alt: "The Check the 1 statement button, marked.",
    open: { to: "financial?view=overview", target: ["text=Check the"] },
  },
  {
    title: "Spot-check the calls Loupe made",
    body: "Where a statement does not print a value outright, Loupe makes a call and lists it. Mark each one Looks right or correct it. Check and correct what Loupe read walks through this.",
    expect: "49 calls Loupe made for you, 49 open.",
    shot: "fin-calls",
    alt: "The Spot-check Loupe card, 49 calls Loupe made for you, marked.",
    open: { to: "financial?view=overview", target: ["text=Spot-check"] },
  },
]

/** Load a phone and see whose it is. */
export const PHONE_IN: TutorialStep[] = [
  {
    title: "Add the phone report",
    body: "On Evidence, Add phone report takes the extraction as a folder or a ZIP. Reading starts by itself; Jobs shows its stage.",
    expect: "Six phone reports on the demo case, PH1 to PH6, each Processed.",
    shot: "ev-phone-add",
    alt: "The Add phone report (folder or ZIP) button, marked.",
    open: { to: "evidence", target: ["text=Add phone report"] },
  },
  {
    title: "Open Phones",
    body: "Phones lists every phone in the case with what it holds. Open one to see who used it.",
    expect: "Phone 1 to Phone 6. Phone 3 is the prepaid phone from the tow truck's glovebox: 81 messages, 10 calls, 64 locations.",
    shot: "ph-index",
    alt: "The Phones list with Phone 3 marked.",
    open: { to: "phones", target: ["text=Phone 3"] },
  },
  {
    title: "Check it read in full",
    body: "The phone's summary says whether the report was read in full and lists what needs a person's decision, such as a missing time zone.",
    expect: "Read in full: 448 records, 29 February to 16 June 2024, 9 apps. 2 things need a decision, the first that the phone recorded no time zone.",
    shot: "ph-summary",
    alt: "Phone 3's summary page with its heading marked and the Needs a decision box below.",
    open: { to: "phones" },
  },
  {
    title: "See who the phone talks to",
    body: "Top people by contact lists the numbers the phone was in touch with most. A name is the one the phone saved, not a person Loupe confirmed.",
    expect: "D.O. (+1 443-555-0142): 45 messages and calls; L (+1 410-555-0161): 24; G (+1 410-555-0171): 22. Only three contacts, and none is Mateo Ruiz.",
    shot: "ph-summary",
    alt: "Phone 3's summary with Top people by contact.",
    open: { to: "phones" },
  },
  {
    title: "Link the phone to a person",
    body: "Link the owner to a person ties the phone to a dossier. Until a person links it, the phone's owner is a suggestion and every screen says so.",
    expect: "Link the owner to a person, beside Add to a device dossier, on Phone 3's summary.",
    shot: "ph-summary",
    alt: "Phone 3's summary page with its action buttons.",
    open: { to: "phones" },
  },
]

/** Get back something deleted. */
export const DELETED: TutorialStep[] = [
  {
    title: "Open Deleted items",
    body: "On Evidence, Deleted items sits under the folders. Anything deleted in the case waits there for 30 days: files, folders, casework and links.",
    expect: "Deleted items under the documents and statements folders.",
    shot: "ev-deleted",
    alt: "Deleted items in the Evidence folder list, marked.",
    open: { to: "evidence", target: ['[data-guide="evidence-deleted"]'] },
  },
  {
    title: "See who deleted what",
    body: "Each item says what it was, when it was deleted, by whom, and how many days are left to restore it. Until then it is hidden from every screen, search and the assistant.",
    expect: "One deleted theory, T4 The glovebox phone entered the truck on 8 June 2024 at 22:30, with who deleted it, when, and the days left to restore it.",
    shot: "ev-deleted-list",
    alt: "The Deleted items list, marked.",
    open: { to: "evidence", target: ['[data-guide="evidence-deleted"]'] },
  },
  {
    title: "Restore it",
    body: "Restore brings the item back exactly as it was, with everything that hung off it. Only the case owner or an admin can restore or remove items for good.",
    expect: "A Restore button beside each item, for the case owner or an admin.",
    shot: "ev-deleted-list",
    alt: "The Deleted items list.",
    open: { to: "evidence", target: ['[data-guide="evidence-deleted"]'] },
  },
  {
    title: "Graph items have their own list",
    body: "Items deleted from the graph go to the graph's Deleted items, the bin button among its tools. Restore them from there the same way.",
    expect: "The Deleted items button among the graph's tools.",
    shot: "gr-deleted",
    alt: "The graph's Deleted items button, marked.",
    open: { to: "graph", target: ['[aria-label="Deleted items"]'] },
  },
]

/** Report and export. */
export const REPORTS: TutorialStep[] = [
  {
    title: "Open Reports",
    body: "Open Reports from the side menu. A casework report holds the case's findings with what each cites, then its theories and notes, in the order you set.",
    expect: "Reports with Financial reports and Casework report.",
    shot: "rp-casework",
    alt: "The Reports page with the Casework report marked.",
    open: { to: "reports", target: ['[data-guide="reports-casework"]'] },
  },
  {
    title: "Set the order and the marking",
    body: "Move Findings, Theories and Notes up or down, and choose a marking: none, Confidential, or Privileged and confidential. The marking is your choice, not a legal ruling.",
    expect: "1. Findings, 2. Theories, 3. Notes, and Marking: No privilege marking.",
    shot: "rp-casework",
    alt: "The Casework report's order and marking.",
    open: { to: "reports", target: ['[data-guide="reports-casework"]'] },
  },
  {
    title: "Export the casework report",
    body: "Export casework report (PDF) writes the report. Each cited item shows whether it supports or contradicts, who added it and its production numbers; model readings are marked as such.",
    expect: "A PDF with the demo case's three theories, T1 to T3, and their evidence for and against.",
    shot: "rp-casework",
    alt: "The Export casework report (PDF) button.",
    open: { to: "reports", target: ['[data-guide="reports-casework"]'] },
  },
  {
    title: "Build a financial report",
    body: "Create a report from financial findings collects the findings saved from the ledger, with the payments behind each and the versions of each note.",
    expect: "No saved financial reports yet on the demo case.",
    shot: "rp-financial",
    alt: "Financial reports with its Create a report from financial findings button.",
    open: { to: "reports", target: ['[data-guide="reports-financial"]'] },
  },
  {
    title: "Export the payments",
    body: "On Transactions, Download CSV writes the payments in view, with any filter you set. Notes CSV writes your notes on them.",
    expect: "Download CSV (6) after a search for POCKETWIRE.",
    shot: "money-pocketwire",
    alt: "Transactions searched for POCKETWIRE, with Download CSV (6) beside the search.",
    open: { to: "financial?view=transactions", target: ["text=Download CSV"] },
  },
]

/** Search the whole case. */
export const SEARCH: TutorialStep[] = [
  {
    title: "Open the case search",
    body: "Press Ctrl+K, or Search this case in the side menu. One box searches every document, payment, message and name.",
    expect: "The search box over the case home.",
    shot: "se-box",
    alt: "The case search box open.",
    open: { to: "workspace", target: ['[data-guide="case-search"]'] },
  },
  {
    title: "Search exact words",
    body: "Type a name or a word and press Enter for every hit. Each hit shows the file, the page and the words around it.",
    expect: "Documents and transcripts matching Kell: 42 matches, starting with bay4-lease-2023-10-01.pdf, page 1.",
    shot: "se-words",
    alt: "Search results for Kell with the heading 42 matches marked.",
    open: { to: "search?q=Kell", target: ['[data-guide="search-heading"]'] },
  },
  {
    title: "Search by meaning",
    body: "Type a question in your own words. By meaning finds passages that say the same thing in other words, graded, each with why it matched.",
    expect: "By meaning results for “where were the stolen goods kept”, best first.",
    shot: "se-meaning",
    alt: "The search box with By meaning results marked.",
    open: { to: "workspace", target: ['[data-guide="case-search"]'] },
  },
  {
    title: "Keep what you found",
    body: "Tick hits and press Add to… to file them with a theory, a dossier or a finding, or to Corroborate them.",
    expect: "Add to… above the 42 hits for Kell.",
    shot: "se-words",
    alt: "Search results with the Add to… button.",
    open: { to: "search?q=Kell", target: ['[data-guide="search-add"]'] },
  },
  {
    title: "Count words on every phone",
    body: "Save words from the search box with Save as keyword list. A keyword list runs on every phone in the case, including phones added later.",
    expect: "No keyword list is saved in the demo case yet.",
    shot: "kw-lists",
    alt: "Keyword lists, with the explanation of how lists run.",
    open: { to: "keyword-lists", target: ['[data-guide="keywords-intro"]'] },
  },
]
