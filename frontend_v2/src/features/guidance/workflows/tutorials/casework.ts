import type { TutorialStep } from "../types"

const THEORIES = "workspace?view=casework&kind=theory"

/** Steps every theory workflow shares: the list of theories and one theory open. */
const OPEN_THEORIES: TutorialStep = {
  title: "Open the theories",
  body: "Open Workspace, then Casework and Theories. Each theory is a working explanation to test as the evidence develops.",
  expect: "3 theories: T1, the State's (Mateo Ruiz fenced the goods in bay 4), T2, the defence's (Kell's operation), and T3 (Desmond Okafor as the inside man).",
  shot: "ws-theories",
  alt: "The theories in Casework, with T2 marked.",
  open: { to: THEORIES, target: ["text=New theory"] },
}
const OPEN_ONE: TutorialStep = {
  title: "Open a theory",
  body: "Click a theory to open it. Each linked item says whether it supports it, contradicts it or is context.",
  expect: "T2 with its linked items, among them Kell's phone and the glovebox phone, and 6 more.",
  shot: "ws-theory",
  alt: "Theory T2 open, with its linked items marked.",
  open: { to: THEORIES, target: ['[data-guide="theory-links"]'], then: "Click a theory in the list to open it." },
}

/** Test a theory with the evidence for and against. */
export const THEORY: TutorialStep[] = [
  OPEN_THEORIES,
  OPEN_ONE,
  {
    title: "Set for beside against",
    body: "For and against shows what supports the theory next to what contradicts it, each with why it was added.",
    expect: "T2's supporting items beside the items that tell against it.",
    shot: "ws-theory-compare",
    alt: "Theory T2 with For and against marked.",
    open: { to: THEORIES, target: ['[data-guide="theory-compare"]'], then: "Click a theory in the list to open it." },
  },
  {
    title: "Add evidence from any screen",
    body: "Add to theory sits beside every payment, event, message and search hit. Pick the theory and say whether the item supports or contradicts it.",
    expect: "Add to theory… in a payment's details, beside Corroborate and Open original statement.",
    shot: "money-details",
    alt: "A payment's details with its buttons, Add to theory among them.",
    open: { to: "financial?view=transactions", target: ["text=Add to theory", "text=▸ Details"], then: "Open Details on a payment: Add to theory is inside." },
  },
  {
    title: "Read it as a whole",
    body: "Reading & analysis shows every addition with why it was chosen, other explanations, and what breaks the theory.",
    expect: "Reading & analysis on T2, with What breaks this theory inside it.",
    shot: "ws-theory-reading",
    alt: "Theory T2's Reading & analysis open, with What breaks this theory marked.",
    open: { to: THEORIES, target: ['[data-guide="theory-reading"]'], then: "Click a theory in the list to open it." },
  },
  {
    title: "Turn it into a finding",
    body: "When the theory holds up, Convert to finding turns it into a finding and carries its linked items with it, ready for the report.",
    expect: "Convert to finding on T2.",
    shot: "ws-theory-convert",
    alt: "Theory T2 with Convert to finding marked.",
    open: { to: THEORIES, target: ['[data-guide="theory-convert"]'], then: "Click a theory in the list to open it." },
  },
]

/** What breaks this theory (also the assistant's guided workflow of that name). */
export const DISCONFIRM: TutorialStep[] = [
  OPEN_THEORIES,
  OPEN_ONE,
  {
    title: "Look for what breaks it",
    body: "In Reading & analysis, What breaks this theory: Look for what breaks it plans reads across the whole case for what tells against each thing the theory expects. Run them, all or only the first few.",
    expect: "What breaks this theory inside T2's Reading & analysis, with its counter-arguments counted by what a person accepted, rejected or left waiting.",
    shot: "ws-theory-reading",
    alt: "What breaks this theory, marked, inside theory T2.",
    open: { to: THEORIES, target: ['[data-guide="theory-reading"]'], then: "Click a theory in the list to open it." },
  },
  {
    title: "Ask for other explanations",
    body: "Red cell: Look for other explanations sends the theory's evidence, without the theory and with names replaced, to a different model, which lists other explanations. Each waits in Agent proposals for a person.",
    expect: "Red cell beside What breaks this theory in T2's Reading & analysis.",
    shot: "ws-theory-reading",
    alt: "Theory T2's Reading & analysis.",
    open: { to: THEORIES, target: ['[data-guide="theory-reading"]'], then: "Click a theory in the list to open it." },
  },
  {
    title: "Or ask the assistant to sweep",
    body: "Agent, new thread, Or start a guided workflow: press Show 9 more workflows, then Use on What breaks this theory, type the theory's title, then Start workflow.",
    expect: "18. What breaks this theory: Ready, all 3 steps can run.",
    shot: "ag-wf-disconfirm-theory",
    alt: "The assistant's guided workflow What breaks this theory opened with Use.",
    open: { to: "agent", target: ['[aria-label="Use workflow What breaks this theory"]', "text=Show 9 more workflows"], then: "Press Show 9 more workflows, then Use on What breaks this theory." },
  },
  {
    title: "Decide on each counter-argument",
    body: "Every counter-argument is a proposal. Open its cited source, then accept or reject it; only what a person accepts joins the theory.",
    expect: "On the demo case, the $650 answer ends: Source check: 16 of 20 citations support their sentence; 4 support part of it.",
    shot: "ag-source",
    alt: "An assistant answer on the demo case with its Source check marked.",
    open: { to: "workspace?view=proposals" },
  },
]

/** Corroborate: how could these items be linked? */
export const CORROBORATE: TutorialStep[] = [
  {
    title: "Mark the items as possibly related",
    body: "Press Corroborate beside Add to theory on any payment, event, message, map area or search hit. Loupe saves them as one group and checks it against the records.",
    expect: "Corroborate in the details of the Pocketwire payments to Lena Marsh and Desmond Okafor.",
    shot: "co-payment",
    alt: "A payment's details with the Corroborate button marked.",
    open: { to: "financial?view=transactions", target: ["text=Corroborate", "text=▸ Details"], then: "Open Details on a payment: Corroborate is inside, and its result opens on a page of its own." },
  },
  {
    title: "Read the result",
    body: "The result says what occurs together in the records, never why: the items, the pairs, and how many candidate links were found at each strength.",
    expect: "6 items marked as possibly related: 15 pairs, 8 candidate links (0 strong, 4 moderate, 3 weak, 1 faint), 9 pairs with no link found.",
    shot: "co-header",
    alt: "A Corroborate result with its heading and counts marked.",
    open: { to: "financial?view=transactions", target: ["text=Corroborate", "text=▸ Details"], then: "Open Details on a payment: Corroborate is inside, and its result opens on a page of its own." },
  },
  {
    title: "Check each candidate link",
    body: "Each link says why it was found and gives the chance of it happening by chance on the case's ordinary days. The strongest come first; weak links are labelled weak.",
    expect: "Moderate, Order of events: 500.00 USD to Lena Marsh on 13 April 2024, a phone position at 03:30 that night, then 1,200.00 USD to Desmond Okafor on 14 April. By chance, both would fall on the same day on 3.3% of days.",
    shot: "co-result",
    alt: "The candidate links, marked, each with its strength and the chance.",
    open: { to: "financial?view=transactions", target: ["text=Corroborate", "text=▸ Details"], then: "Open Details on a payment: Corroborate is inside, and its result opens on a page of its own." },
  },
  {
    title: "See where no link was found",
    body: "Each pair with no link says what was searched. No link found is what was searched, not proof that no link exists.",
    expect: "9 pairs with no link found, each with what was searched.",
    shot: "co-nolink",
    alt: "Pairs with no link found, marked.",
    open: { to: "financial?view=transactions", target: ["text=Corroborate", "text=▸ Details"], then: "Open Details on a payment: Corroborate is inside, and its result opens on a page of its own." },
  },
  {
    title: "Ask how they could be linked",
    body: "Ask how they could be linked has the assistant draft explanations, each with the records for and against. They are model readings: accept one into a theory as supports or contradicts. Export report (PDF) writes the whole result.",
    expect: "Ask how they could be linked, Export report (PDF) and Run again above the items.",
    shot: "co-actions",
    alt: "The result's buttons, Ask how they could be linked among them, marked.",
    open: { to: "financial?view=transactions", target: ["text=Corroborate", "text=▸ Details"], then: "Open Details on a payment: Corroborate is inside, and its result opens on a page of its own." },
  },
  {
    title: "Gather a selection across screens",
    body: "With the new Corroborate on, what you pick on any screen gathers in a tray in the corner and stays as you move between screens. Corroborate then offers questions about the selection, each with its count.",
    expect: "The Corroborate tray in the corner of the Transactions screen.",
    shot: "co-tray",
    alt: "The Corroborate tray, marked.",
    open: { to: "financial?view=transactions", target: ['[data-guide="corroborate-tray"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Or ask the assistant",
    body: "Agent, new thread, Or start a guided workflow: press Show 9 more workflows, then Use on Corroborate, name the group, then Start workflow. It states what the analysis found, names competing explanations and says where no link was found.",
    expect: "19. Corroborate: Ready, all 7 steps can run.",
    shot: "ag-wf-link-group",
    alt: "The assistant's guided workflow Corroborate opened with Use.",
    open: { to: "agent", target: ['[aria-label="Use workflow Corroborate"]', "text=Show 9 more workflows"], then: "Press Show 9 more workflows, then Use on Corroborate." },
  },
]

/** Check a claim against the phones (behind the new Corroborate). */
export const CLAIM: TutorialStep[] = [
  {
    title: "Open Check a claim",
    body: "In the Corroborate tray, Check a claim takes a sentence someone said, in their words.",
    expect: "Check a claim in the Corroborate tray.",
    shot: "co-claim",
    alt: "The Corroborate tray with Check a claim marked.",
    open: { to: "workspace", target: ['[data-guide="corroborate-claim"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Type the claim",
    body: "Type the sentence, for example “I was home all evening on 3 May 2024”. Loupe reads who, when, where and what from it, each with the words it came from.",
    expect: "Who, when, where and what chips under the sentence, each editable.",
    shot: "co-claim",
    alt: "The Corroborate tray with Check a claim.",
    open: { to: "workspace", target: ['[data-guide="corroborate-claim"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Confirm what it read",
    body: "Correct any chip and confirm. Nothing is checked until you confirm: an unconfirmed claim is refused.",
    expect: "The confirmed claim ready to check against the phones.",
    shot: "co-claim",
    alt: "The Corroborate tray with Check a claim.",
    open: { to: "workspace", target: ['[data-guide="corroborate-claim"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Read the answer",
    body: "Loupe weighs the claim against the phones and answers Fits, Contradicts or Can't tell, with the records behind it and what was searched. A claim about a place with no position reads Can't tell.",
    expect: "Fits, Contradicts or Can't tell, with the records it rests on.",
    shot: "co-tray",
    alt: "The Corroborate tray.",
    open: { to: "workspace", target: ['[data-guide="corroborate-tray"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Check a line of a theory",
    body: "In a theory's Reading & analysis, a line that says where someone was offers Corroborate this claim, which checks that line the same way.",
    expect: "Reading & analysis on theory T2.",
    shot: "ws-theory-reading",
    alt: "Theory T2's Reading & analysis.",
    open: { to: THEORIES, target: ['[data-guide="theory-reading"]'], then: "Click a theory in the list to open it." },
    switch: "corroborate-v2",
  },
]

/** Work through leads (behind the new Corroborate). */
export const LEADS: TutorialStep[] = [
  {
    title: "Open Leads",
    body: "Leads, in the side menu, lists patterns across every kind of record that may show people acting together, each graded against the case's ordinary days.",
    expect: "24 leads: Contact 4, Together 6, Money 3, Words and files 5, Silence and deletion 7.",
    shot: "leads-list",
    alt: "The Leads page with Look for leads now marked.",
    open: { to: "leads", target: ['[data-guide="leads-find"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Pick one kind",
    body: "Pick a kind to show only those leads, with the count of each.",
    expect: "Contact, Together, Money, Words and files, Access logs and Silence and deletion, each with its count.",
    shot: "leads-filters",
    alt: "The kinds of lead, marked.",
    open: { to: "leads", target: ['[data-guide="leads-filters"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Read the strongest first",
    body: "The strongest leads come first, each with what raises and lowers its grade and the records behind it.",
    expect: "Strong link, Contact: Lena Marsh and Desmond Okafor are each in contact with the user of Phone 3.",
    shot: "leads-list",
    alt: "The list of leads, strongest first.",
    open: { to: "leads", target: ['[data-guide="leads-list"]'] },
    switch: "corroborate-v2",
  },
  {
    title: "Look again after new material",
    body: "Look for leads now reads the whole case again. A case read in under 20 minutes is looked at again by itself when new material arrives.",
    expect: "Look for leads now at the top of the page.",
    shot: "leads-list",
    alt: "Look for leads now, marked.",
    open: { to: "leads", target: ['[data-guide="leads-find"]'] },
    switch: "corroborate-v2",
  },
]

/** Build a picture of a person. */
export const DOSSIER: TutorialStep[] = [
  {
    title: "Open Dossiers",
    body: "Open Dossiers from the side menu. A dossier brings a subject's numbers, accounts, addresses and casework together.",
    expect: "6 dossiers: Gary Penn, Travis Kell, Mateo Ruiz, Lena Marsh, Brianna Cole and Desmond Okafor.",
    shot: "do-list",
    alt: "The list of dossiers, marked.",
    open: { to: "dossiers", target: ['[data-guide="dossiers-list"]'] },
  },
  {
    title: "Open one",
    body: "Click a dossier. Its tabs hold what is known about the subject and where each piece came from.",
    expect: "Travis Kell's dossier: his mobile, +1 410 555 0121, and home address, each marked Investigator recorded, and his proffer of 20 June 2024 under Interviews at a glance.",
    shot: "do-kell",
    alt: "Travis Kell's dossier with its tabs marked.",
    open: { to: "dossiers", target: ['[data-guide="dossiers-detail-tabs"]', '[data-guide="dossiers-list"]'], then: "Click a person in the list to open their dossier." },
  },
  {
    title: "Check the phone links",
    body: "A number linked to the subject by Loupe is a suggestion until a person confirms it. Phone identities lists every number and account the phones hold, with the names each phone saved.",
    expect: "On Kell's dossier: Suggested, not reviewed: 3 more identities may be Travis Kell. None is counted here.",
    shot: "do-kell",
    alt: "Travis Kell's dossier.",
    open: { to: "dossiers", target: ['[data-guide="dossiers-views"]'] },
  },
  {
    title: "Find the subject on the graph",
    body: "On the Graph, search for the name. The subject's links to people, companies, accounts and places come from the evidence, each with its source.",
    expect: "553 items and 1,511 links on the graph.",
    shot: "gr-canvas",
    alt: "The graph of the demo case.",
    open: { to: "graph" },
  },
  {
    title: "Start a new dossier",
    body: "New Dossier starts one for a person, company or device. Add to a dossier sits beside every record.",
    expect: "New Dossier at the top of the list.",
    shot: "do-new",
    alt: "The New Dossier button, marked.",
    open: { to: "dossiers", target: ['[data-guide="dossiers-new"]'] },
  },
]

/** See who is linked to whom. */
export const GRAPH: TutorialStep[] = [
  {
    title: "Open the graph",
    body: "Open Graph from the side menu. Each dot is a person, company, account or place found in the evidence; each line is a link between them.",
    expect: "553 of 553 items shown, 1,511 links, 27 types in the legend.",
    shot: "gr-canvas",
    alt: "The graph of the demo case.",
    open: { to: "graph" },
  },
  {
    title: "Zoom and focus",
    body: "Zoom in, then click a dot to see where it comes from. Right-click it to expand its links or merge duplicates.",
    expect: "Zoom in, Zoom out and Fit graph to view beside the graph.",
    shot: "gr-canvas",
    alt: "The graph with its zoom controls.",
    open: { to: "graph", target: ['[aria-label="Zoom in"]'] },
  },
  {
    title: "See who was in contact",
    body: "People in contact lists each pair of people on the phones who messaged, called or emailed each other, busiest first.",
    expect: "People in contact: 20 pairs of people on the phones.",
    shot: "gr-people",
    alt: "People in contact, marked.",
    open: { to: "graph", target: ['[data-guide="graph-people-in-contact"]'] },
  },
  {
    title: "Check the names in a table",
    body: "Table lists every item with its type, links and sources, to find duplicates and check where each name came from.",
    expect: "768 entities with their type, connections and sources.",
    shot: "table-grid",
    alt: "The Table with its tool bar marked.",
    open: { to: "table", target: ['[data-guide="table-toolbar"]'] },
  },
  {
    title: "Keep what matters",
    body: "Select dots and press Add to theory, so the reason you chose them stays with them.",
    expect: "Select by clicking and Drag select among the graph's tools.",
    shot: "gr-canvas",
    alt: "The graph with its selection tools.",
    open: { to: "graph", target: ["text=Add to theory", '[aria-label="Drag select"]'], then: "Select dots: click one, or Drag select round several. Add to theory is in the panel beside the graph." },
  },
]

/** Defence and review: test the other side's timeline. */
export const DEFENCE_REVIEW: TutorialStep[] = [
  {
    title: "Set the other side's case down as a theory",
    body: "Write the other side's account as a theory, so every item can be weighed for and against it.",
    expect: "T1, the State's theory: Mateo Ruiz fenced the goods in bay 4; the $650 payments were his cut; the glovebox phone was his.",
    shot: "ws-theories",
    alt: "The theories in Casework.",
    open: { to: THEORIES, target: ["text=New theory"] },
  },
  {
    title: "Read the witness accounts",
    body: "Each dossier holds the subject's interviews, under Interviews. A summary or comparison drafted by the model waits as a proposal until a person accepts it.",
    expect: "Kell's dossier lists his proffer session of 20 June 2024 under Interviews at a glance, with its transcript, kell-proffer-transcript-2024-06-20.docx.",
    shot: "do-kell",
    alt: "Travis Kell's dossier.",
    open: { to: "dossiers", target: ['[data-guide="dossiers-detail-tabs"]', '[data-guide="dossiers-list"]'], then: "Click a person in the list to open their dossier." },
  },
  {
    title: "Check what rests on Loupe's calls",
    body: "Spot-check Loupe lists the calls Loupe made on statements. A conclusion resting on an unchecked call is weaker than one resting on a printed value.",
    expect: "49 calls Loupe made for you, 49 open.",
    shot: "fin-calls",
    alt: "The Spot-check Loupe card, marked.",
    open: { to: "financial?view=overview", target: ["text=Spot-check"] },
  },
  {
    title: "Find the gaps",
    body: "Which months do we have? shows each account's missing months. A gap is no record, and the screen says why.",
    expect: "May 2024 Missing on one account: Kell's May statement, whose second page is missing.",
    shot: "fin-coverage",
    alt: "The Check dates and missing statements button, marked.",
    open: { to: "financial?view=overview", target: ["text=Check dates and missing statements"] },
  },
  {
    title: "Ask the assistant to test it line by line",
    body: "Agent, new thread, Or start a guided workflow: Use on Defence and review, then Start workflow. It proposes each line of the other side's timeline as a claim, in its exact words, for you to confirm before it is tested.",
    expect: "10. Defence and review: Ready, all 7 steps can run.",
    shot: "ag-wf-defence-review",
    alt: "The assistant's guided workflow Defence and review opened with Use.",
    open: { to: "agent", target: ['[aria-label="Use workflow Defence and review"]'] },
  },
  {
    title: "Confirm each claim and finding",
    body: "Nothing it proposes counts until you confirm it. Each finding quotes the other side's statement and the source that bears on it.",
    expect: "On the demo case, the $650 answer ends: Source check: 16 of 20 citations support their sentence; 4 support part of it.",
    shot: "ag-source",
    alt: "An assistant answer with its Source check marked.",
    open: { to: "workspace?view=proposals" },
  },
]
