import type { GuideId } from "./guides"
import type { ActionKind } from "./next-steps"
import type { TourArea } from "./tours"

/**
 * Every feature a person can see or use in the app, with the guidance that explains it (lx-guidecover, Neil 23 Nov).
 * guidance-features.test.ts fails when a feature here has no guide section, no tour step or next step, no tooltip on
 * its screen, a glossary term that is missing, or a guide whose copy in docs/user-guide differs. A new feature is added
 * here with its guidance in the same change.
 *
 * - guide: the guide and the `##` heading of its section (the user documentation; docs/user-guide holds the same text).
 * - tour: the tour (by area) and the title of the step that shows it; or next: the next-step card it leads to.
 * - files: the screen files (under src/) whose controls carry the feature's tooltips or Learn more links; or
 *   noControl: why the feature has no control of its own (it is how the agent writes its answer, for example).
 * - terms: glossary headings the feature's screen or guide section uses.
 * - switch: the setting a feature waits behind; its guidance waits behind the same setting.
 */
export interface FeatureGuidance {
  id: string
  name: string
  since: string
  switch?: "corroborate-v2" | "phone_together"
  guide: { id: GuideId; heading: string }
  tour?: { area: TourArea; step: string }
  next?: ActionKind
  files?: string[]
  noControl?: string
  terms: string[]
}

const BEFORE = "before 17 Nov 2026"
const NOV17 = "17 Nov 2026"
const NOV18 = "18 Nov 2026"
const NOV20 = "20 Nov 2026"
const NOV22 = "22 Nov 2026"
const ANSWER = "Part of how the agent reads the case and writes its answer; the person sees it in the answer text, not on a control."

export const FEATURES: FeatureGuidance[] = [
  // Case home, casework and reports
  { id: "case-home", name: "Case home: theories, findings, notes and tasks", since: BEFORE, guide: { id: "case-home", heading: "Main controls" }, tour: { area: "workspace", step: "This is the case home" }, files: ["features/guidance/StartHere.tsx", "features/workspace/components/CaseBriefPanel.tsx"], terms: ["Workspace", "Verified period"] },
  { id: "start-here", name: "Start here steps", since: BEFORE, guide: { id: "case-home", heading: "Start here" }, tour: { area: "workspace", step: "This is the case home" }, files: ["features/guidance/StartHere.tsx"], terms: [] },
  { id: "guide-menu", name: "Guide menu, tours and guides", since: BEFORE, guide: { id: "case-home", heading: "The Guide menu" }, tour: { area: "workspace", step: "Help is always here" }, files: ["features/guidance/GuideMenu.tsx", "features/guidance/CaseGuidanceBar.tsx"], terms: [] },
  { id: "step-history", name: "Your steps in the bottom bar", since: BEFORE, guide: { id: "case-home", heading: "Your steps in the bottom bar" }, tour: { area: "workspace", step: "Your steps, one click back" }, files: ["features/guidance/history/HistoryStrip.tsx"], terms: ["Trail"] },
  { id: "theory", name: "Theories: for and against, links to review, findings", since: BEFORE, guide: { id: "theories", heading: "Weigh what supports and contradicts a theory" }, tour: { area: "theory", step: "For and against" }, files: ["features/workspace/components/CaseworkDetailSheet.tsx"], terms: ["Supports Contradicts and Context", "Links to review"] },
  { id: "changed-since-cited", name: "Changed since cited and Merged from", since: BEFORE, guide: { id: "theories", heading: "Changed since cited" }, tour: { area: "theory", step: "What bears on it" }, files: ["features/workspace/components/CaseworkDetailSheet.tsx"], terms: ["Changed since cited", "Merged from"] },
  { id: "add-to-theory", name: "Add to theory from any screen", since: BEFORE, guide: { id: "theories", heading: "Add an item to a theory" }, next: "theory-addition", files: ["features/theory/AddToTheory.tsx"], terms: [] },
  { id: "reports", name: "Reports: financial reports and the casework report", since: BEFORE, guide: { id: "case-home", heading: "Reports" }, tour: { area: "reports", step: "The casework report" }, next: "report-built", files: ["features/reports/components/ReportsPage.tsx", "features/reports/components/CaseworkReportCard.tsx"], terms: [] },
  { id: "case-settings", name: "Case settings, address lookup, picture blur, whole-case export", since: BEFORE, guide: { id: "case-home", heading: "Case settings" }, tour: { area: "settings", step: "The case's details" }, files: ["features/cases/components/CaseSettingsPage.tsx", "features/cases/components/AddressLookupSetting.tsx"], terms: ["Address lookup"] },
  { id: "deleted-items", name: "Deleted items: restore any deleted work for 30 days", since: BEFORE, guide: { id: "evidence", heading: "Delete and restore with Deleted items" }, tour: { area: "evidence", step: "Nothing deleted is lost" }, next: "deleted", files: ["features/evidence/components/FolderTreeSidebar.tsx"], terms: ["Deleted items"] },

  // Evidence
  { id: "evidence-upload", name: "Upload files and folders", since: BEFORE, guide: { id: "evidence", heading: "Upload files and folders" }, tour: { area: "evidence", step: "Your files, as they came in" }, files: ["features/evidence/components/FileListToolbar.tsx"], terms: [] },
  { id: "evidence-process", name: "Process files and follow Jobs", since: BEFORE, guide: { id: "evidence", heading: "Process files" }, tour: { area: "evidence", step: "Process a file to read it" }, next: "document-processed", files: ["features/evidence/components/JobsPanel.tsx", "features/evidence/components/ProcessingLogViewer.tsx"], terms: [] },
  { id: "evidence-send-locked", name: "A send that cannot start says why", since: NOV17, guide: { id: "evidence", heading: "When a send cannot start" }, tour: { area: "evidence", step: "Process a file to read it" }, files: ["features/evidence/components/JobsPanel.tsx", "features/evidence/components/ProcessingLogViewer.tsx"], terms: [] },
  { id: "phone-readiness", name: "Phone report readiness card", since: BEFORE, guide: { id: "evidence", heading: "Phone report readiness" }, tour: { area: "evidence", step: "Work in progress" }, next: "phone-imported", files: ["features/evidence/components/PhoneReadinessCard.tsx"], terms: [] },
  { id: "large-videos", name: "Large videos and File missing", since: BEFORE, guide: { id: "evidence", heading: "File missing" }, tour: { area: "evidence", step: "Photos, videos and missing files" }, files: ["features/evidence/components/FileRow.tsx"], terms: ["File missing"] },
  { id: "photo-data", name: "Photo data, photos on the Timeline and Map", since: BEFORE, guide: { id: "evidence", heading: "Photo data" }, tour: { area: "evidence", step: "Photos, videos and missing files" }, files: ["features/evidence/components/PhotoDataPanel.tsx"], terms: ["Photo data"] },
  { id: "unchecked-claims", name: "Unchecked claims on a file", since: BEFORE, guide: { id: "evidence", heading: "Unchecked claims on a file" }, tour: { area: "evidence", step: "Your files, as they came in" }, files: ["features/evidence/components/EvidenceContextSidebar.tsx"], terms: ["Unchecked claims"] },
  { id: "text-workbench", name: "The document text reader", since: BEFORE, guide: { id: "evidence", heading: "The document text reader" }, tour: { area: "text", step: "The page as it came in" }, files: ["features/evidence/components/TextWorkbenchPage.tsx"], terms: ["OCR"] },
  { id: "document-dates", name: "Dates read from a document (Read by Loupe, not confirmed)", since: NOV20, guide: { id: "evidence", heading: "Dates read from a document" }, tour: { area: "evidence", step: "Process a file to read it" }, files: ["features/evidence/components/DocumentDatesPanel.tsx"], terms: ["Read by Loupe not confirmed"] },

  // Graph and table
  { id: "graph", name: "Graph: who is linked to whom", since: BEFORE, guide: { id: "graph", heading: "Main controls" }, tour: { area: "graph", step: "Who is linked to whom" }, files: ["features/graph/components/GraphToolbar.tsx", "features/graph/components/NodeDetailSheet.tsx"], terms: [] },
  { id: "people-in-contact", name: "People in contact on the Graph", since: BEFORE, guide: { id: "graph", heading: "People in contact" }, tour: { area: "graph", step: "People in contact" }, files: ["features/graph/components/PhoneCommunicationEdges.tsx"], terms: ["People in contact"] },
  { id: "graph-merge", name: "Find and merge items that may be the same", since: BEFORE, guide: { id: "graph", heading: "Merge items" }, next: "merge-done", files: ["features/graph/components/SimilarEntitiesView.tsx", "features/graph/components/MergeLineage.tsx"], terms: ["Merged from"] },
  { id: "table", name: "The names table", since: BEFORE, guide: { id: "graph", heading: "The names table" }, tour: { area: "table", step: "Every entity in rows" }, files: ["features/table/components/TableToolbar.tsx", "features/table/components/BulkActionsBar.tsx"], terms: [] },
  { id: "graph-overlap", name: "People, go-betweens and documents on the Graph", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "People, go-betweens and documents on the Graph" }, tour: { area: "graph", step: "People, go-betweens and documents" }, files: ["features/overlap/graph/OverlapGraph.tsx"], terms: ["Go-between"] },

  // Timeline and Map
  { id: "timeline", name: "Timeline: everything in date order", since: BEFORE, guide: { id: "timeline", heading: "Main controls" }, tour: { area: "timeline", step: "Everything in date order" }, files: ["features/timeline/components/TimelineToolbar.tsx"], terms: [] },
  { id: "timeline-undated", name: "Events with no time recorded", since: BEFORE, guide: { id: "timeline", heading: "Events with no time recorded" }, tour: { area: "timeline", step: "Events with no time" }, files: ["features/timeline/components/TimelineToolbar.tsx"], terms: [] },
  { id: "timeline-phone-lens", name: "The phone lens and the window around a moment", since: BEFORE, guide: { id: "timeline", heading: "The phone lens" }, tour: { area: "timeline", step: "Choose what to show" }, files: ["features/timeline/lens/PhoneLens.tsx"], terms: ["Phone lens"] },
  { id: "map", name: "Map: places, areas and phones seen in an area", since: BEFORE, guide: { id: "map", heading: "Draw an area" }, tour: { area: "map", step: "Draw an area" }, files: ["features/map/components/MapToolbar.tsx"], terms: [] },
  { id: "map-review", name: "Places that need review", since: BEFORE, guide: { id: "map", heading: "Check places that need review" }, tour: { area: "map", step: "Where things happened" }, files: ["features/map/components/NeedsReviewPanel.tsx", "features/map/components/MapToolbar.tsx"], terms: [] },
  { id: "map-routes", name: "Phone positions and routes", since: BEFORE, guide: { id: "map", heading: "Show routes" }, tour: { area: "map", step: "Each phone's route" }, files: ["features/map/components/MapToolbar.tsx"], terms: ["Show routes"] },
  { id: "area-compare", name: "Compare drawn areas over time", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Compare drawn areas over time" }, tour: { area: "map", step: "Areas over time" }, files: ["features/overlap/area/AreaCompare.tsx"], terms: ["Compare areas over time"] },

  // Phones
  { id: "phones", name: "Phones: each phone in the case", since: BEFORE, guide: { id: "phones", heading: "First look at a phone" }, tour: { area: "phones", step: "Each phone in the case" }, files: ["features/phones/components/RecordPanel.tsx", "features/phones/components/StreamList.tsx"], terms: ["Phone marks and terms"] },
  { id: "phone-layers", name: "Phone layers: switch each phone on or off", since: NOV18, guide: { id: "phones", heading: "Switch phones on and off" }, tour: { area: "phones", step: "Choose the phones" }, next: "layers-changed", files: ["features/phones/ui/PhoneLayers.tsx"], terms: ["Phone layers"] },
  { id: "phones-together", name: "Where phones were together", since: BEFORE, switch: "phone_together", guide: { id: "phones", heading: "See where phones were together" }, tour: { area: "map", step: "Each phone's route" }, files: ["features/phones/ui/PhoneLayers.tsx"], terms: ["Phone layers"] },
  { id: "phone-compare", name: "Compare two phones, or two extractions of one", since: BEFORE, guide: { id: "phones", heading: "Compare two phones, or two extractions of one" }, tour: { area: "analyses", step: "Run the analysis" }, next: "phones-compared", files: ["features/phones/analysis/ApproachLayout.tsx"], terms: [] },
  { id: "phone-source-row", name: "The database row behind a record, and an independent re-read", since: BEFORE, guide: { id: "phones", heading: "See the database row behind a record" }, tour: { area: "phones", step: "Check the report itself" }, files: ["features/phones/components/SourceDatabasePanel.tsx", "features/phones/analysis/ReparsePage.tsx"], terms: ["Read again by an independent tool"] },
  { id: "conversations", name: "Conversations: threads, people and review", since: BEFORE, guide: { id: "phones", heading: "Read a conversation around a date" }, tour: { area: "conversations", step: "Threads or people" }, files: ["features/conversations/ConversationFilters.tsx", "features/conversations/ConversationsPage.tsx"], terms: [] },
  { id: "phone-analyses", name: "Phone analyses", since: BEFORE, guide: { id: "phones", heading: "Find deleted or concealed material" }, tour: { area: "analyses", step: "Analyses across the phones" }, files: ["features/phones/analysis/AnalysesPage.tsx", "features/phones/analysis/ApproachLayout.tsx"], terms: [] },
  { id: "phone-patterns", name: "Phone patterns and key dates", since: BEFORE, guide: { id: "phones", heading: "Test a statement against the phones" }, tour: { area: "pattern", step: "Choose a phone or person" }, files: ["features/pattern/components/KeyDates.tsx", "features/pattern/components/Lanes.tsx"], terms: ["Incidents and ordinary days"] },
  { id: "also-elsewhere", name: "Words also on another phone (Also elsewhere)", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Words also on another phone" }, tour: { area: "conversations", step: "Words also on other phones" }, files: ["features/overlap/conversations/marks.tsx"], terms: ["Also elsewhere", "Stock phrase"] },
  { id: "record-panel-sheet", name: "A phone record opens over the page, as a sheet on a phone-width screen", since: NOV18, guide: { id: "assistant", heading: "Links in an answer" }, tour: { area: "chat", step: "What the answer names" }, files: ["features/phones/ui/DockedPanel.tsx"], terms: [] },

  // Search
  { id: "search-box", name: "The Search box: words and By meaning", since: BEFORE, guide: { id: "search", heading: "Search by meaning" }, tour: { area: "workspace", step: "Search the whole case" }, next: "case-search-done", files: ["features/search/components/MeaningGroup.tsx"], terms: ["By meaning"] },
  { id: "search-results", name: "A full list of hits, saved as a keyword list", since: BEFORE, guide: { id: "search", heading: "Work with a full list of hits" }, tour: { area: "search", step: "Every match, not a sample" }, files: ["features/search/components/SearchResultsPage.tsx"], terms: [] },
  { id: "keyword-lists", name: "Keyword lists", since: BEFORE, guide: { id: "search", heading: "Read keyword lists" }, tour: { area: "keywords", step: "Lists that run on every phone" }, files: ["features/search/components/KeywordListsPage.tsx"], terms: ["Keyword list"] },
  { id: "search-notifications", name: "Search reads phone notifications, a named person's own phone, and citations as words", since: NOV20, guide: { id: "search", heading: "What search by meaning reads" }, tour: { area: "workspace", step: "Search the whole case" }, next: "case-search-done", files: ["features/search/components/MeaningGroup.tsx"], terms: ["By meaning"] },

  // Case assistant
  { id: "agent-ask", name: "Ask the agent a question", since: BEFORE, guide: { id: "assistant", heading: "Ask the agent a question" }, tour: { area: "agent", step: "Ask about the case" }, next: "agent-run-done", files: ["features/agent/components/AgentPage.tsx"], terms: ["Source check"] },
  { id: "deep-investigation", name: "Deep investigation", since: BEFORE, guide: { id: "assistant", heading: "Run a deep investigation" }, tour: { area: "agent", step: "Go deeper" }, next: "agent-run-done", files: ["features/agent/components/DeepSwitch.tsx"], terms: ["Deep investigation"] },
  { id: "agent-tools", name: "Tools for this question", since: BEFORE, guide: { id: "assistant", heading: "Steer the agent with Tools for this question" }, tour: { area: "agent", step: "Steer the tools" }, files: ["features/agent/components/ToolSteeringCard.tsx"], terms: ["Tools for this question", "Not examined"] },
  { id: "agent-rate", name: "Rate an answer", since: BEFORE, guide: { id: "assistant", heading: "Rate an answer" }, tour: { area: "agent", step: "Rate an answer" }, files: ["features/agent/components/AnswerRating.tsx"], terms: [] },
  { id: "source-check", name: "Source check on every answer", since: BEFORE, guide: { id: "assistant", heading: "Check the sources behind an answer" }, tour: { area: "agent", step: "Ask about the case" }, files: ["features/agent/components/AgentPage.tsx"], terms: ["Source check"] },
  { id: "chat", name: "AI chat", since: BEFORE, guide: { id: "assistant", heading: "Ask in AI chat" }, tour: { area: "chat", step: "Ask about the case" }, files: ["features/chat/components/ChatInput.tsx"], terms: [] },
  { id: "answer-links", name: "Answer links open payments, graph items and phone records; links to nothing are removed and counted", since: NOV17, guide: { id: "assistant", heading: "Links in an answer" }, tour: { area: "chat", step: "What the answer names" }, files: ["components/citations/citations.tsx", "features/phones/ui/DockedPanel.tsx"], terms: [] },
  { id: "agent-ledger-search", name: "The agent finds payments by meaning and loose words, names saved on phones, initials and surnames", since: NOV18, guide: { id: "assistant", heading: "How the agent finds payments, names and documents" }, tour: { area: "agent", step: "Ask about the case" }, noControl: ANSWER, terms: ["By meaning"] },
  { id: "phones-around-payments", name: "The agent reads the phones around the payments it reads", since: NOV22, guide: { id: "assistant", heading: "The phones around payments" }, tour: { area: "agent", step: "Ask about the case" }, noControl: ANSWER, terms: [] },
  { id: "photo-text", name: "Text read from photos in the agent's phone record, marked as a machine reading", since: NOV22, guide: { id: "assistant", heading: "Text read from photos in a phone record" }, tour: { area: "agent", step: "Ask about the case" }, noControl: ANSWER, terms: ["Model reading"] },
  { id: "other-identities", name: "A read between two people counts their other identities", since: "23 Nov 2026", guide: { id: "assistant", heading: "Two people and their other identities" }, tour: { area: "agent", step: "Ask about the case" }, noControl: ANSWER, terms: [] },
  { id: "failed-check-draft", name: "A failed source review shows the draft with its flagged lines; Checks this answer did not pass", since: NOV22, guide: { id: "assistant", heading: "When an answer fails a check" }, tour: { area: "agent", step: "Ask about the case" }, noControl: ANSWER, terms: ["Source check"] },
  { id: "every-reading", name: "The agent answers each reading of a question and looks up each part", since: NOV22, guide: { id: "assistant", heading: "Questions with several readings" }, tour: { area: "agent", step: "Ask about the case" }, noControl: ANSWER, terms: [] },

  // Corroborate and Leads
  { id: "corroborate-classic", name: "Corroborate and its report", since: BEFORE, guide: { id: "corroborate", heading: "Start a look" }, tour: { area: "relations", step: "Items you marked as related" }, next: "corroborate-done", files: ["features/relations/LookIntoButton.tsx", "features/relations/RelationsPage.tsx"], terms: ["Corroborate", "Graded likelihood", "No link found"] },
  { id: "corroborate-tray", name: "The selection tray, question menu and scope bar", since: BEFORE, switch: "corroborate-v2", guide: { id: "corroborate", heading: "The selection tray" }, tour: { area: "corroborate", step: "Gather what to check" }, next: "corroborate-done", files: ["features/corroborate/CorroborateTray.tsx"], terms: ["Saved subsets"] },
  { id: "corroborate-levels", name: "Corroborate levels, checks made, gaps and story lanes", since: BEFORE, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Read the level" }, tour: { area: "corroborate", step: "Ask a question of it" }, next: "corroborate-done", files: ["features/corroborate/CorroborateTray.tsx"], terms: ["Corroborate levels", "Checks made", "Story lanes", "Records missing"] },
  { id: "corroborate-claim", name: "Corroborate this claim", since: BEFORE, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Corroborate this claim" }, tour: { area: "corroborate", step: "Check a claim" }, files: ["features/corroborate/CorroborateTray.tsx"], terms: [] },
  { id: "leads", name: "Leads: patterns Loupe found across the case", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Leads" }, tour: { area: "leads", step: "Patterns Loupe found" }, files: ["features/leads/LeadsPage.tsx"], terms: ["Lead", "Coincidence likely", "No link found", "Set aside"] },
  { id: "leads-auto", name: "Leads look again by themselves on new material", since: NOV22, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Leads that keep themselves up to date" }, tour: { area: "leads", step: "Look again" }, files: ["features/leads/LeadsPage.tsx"], terms: ["Lead"] },
  { id: "corroborate-panel", name: "Corroborate from anywhere: the Corroborate page opens from any screen, and Corroborate on a photo", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Corroborate from anywhere" }, tour: { area: "corropanel", step: "Leads already here" }, files: ["features/leads/CorroborateAction.tsx"], terms: ["Lead"] },
  { id: "lead-records", name: "Show a lead's records across screens", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Show a lead's records across screens" }, tour: { area: "leads", step: "See a lead's records" }, files: ["features/leads/LeadsPage.tsx"], terms: ["Lead"] },
  { id: "around-event", name: "Money around an event", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Money around an event" }, tour: { area: "financial", step: "Follow the money" }, files: ["features/overlap/money/AroundEventPage.tsx"], terms: ["Money around an event"] },
  { id: "who-overlaps", name: "Who overlaps with whom", since: NOV18, switch: "corroborate-v2", guide: { id: "corroborate", heading: "Who overlaps with whom" }, tour: { area: "dossiers", step: "Who overlaps with whom" }, files: ["features/overlap/people/OverlapsView.tsx"], terms: ["Who overlaps with whom"] },

  // Dossiers
  { id: "dossiers", name: "Dossiers: one per subject", since: BEFORE, guide: { id: "dossiers", heading: "Read a dossier" }, tour: { area: "dossiers", step: "One dossier per subject" }, files: ["features/dossiers/components/DossierDetailSheet.tsx"], terms: [] },
  { id: "phone-identities", name: "Phone identities and people suggestions", since: BEFORE, guide: { id: "dossiers", heading: "Phone identities" }, tour: { area: "dossiers", step: "Dossiers and phone identities" }, files: ["features/dossiers/components/PhoneIdentitiesTab.tsx", "features/dossiers/components/DossierDetailSheet.tsx"], terms: [] },
  { id: "dossier-addresses", name: "Map positions of dossier addresses", since: NOV20, guide: { id: "dossiers", heading: "Map positions of addresses" }, tour: { area: "dossiers", step: "Open a dossier" }, files: ["features/dossiers/components/DossierContacts.tsx"], terms: ["Read by Loupe not confirmed"] },

  // Financial
  { id: "financial-import", name: "Add a statement PDF, check and confirm its import", since: BEFORE, guide: { id: "financial", heading: "Confirm the statement import" }, tour: { area: "financial", step: "Statements to check" }, next: "statement-imported", files: ["features/financial/components/StatementImportPanel.tsx", "features/financial/components/CandidateFinalizationPanel.tsx"], terms: ["Finalization", "Provisional"] },
  { id: "financial-ledger", name: "Read, filter and correct the ledger", since: BEFORE, guide: { id: "financial", heading: "Read and filter transactions" }, tour: { area: "financial", step: "Every payment" }, next: "correction-saved", files: ["features/financial/components/CorrectableLedger.tsx", "features/financial/components/TransactionTable.tsx"], terms: ["Ledger", "Corrected before import"] },
  { id: "financial-coverage", name: "Statement checks and missing periods", since: BEFORE, guide: { id: "financial", heading: "Check statements and missing periods" }, tour: { area: "financial", step: "Statements to check" }, files: ["features/financial/components/StatementCoverageReview.tsx", "features/financial/components/StatementControlPicker.tsx"], terms: ["Verified period", "Statement control"] },
  { id: "financial-trace", name: "Follow the money in one account and between accounts", since: BEFORE, guide: { id: "financial", heading: "Trace funds between accounts" }, tour: { area: "financial", step: "Follow the money" }, files: ["features/financial/components/AccountFlowPerspective.tsx", "features/financial/components/LedgerTracingWorkbench.tsx"], terms: ["Account perspective", "Counterparty"] },
  { id: "judgement-calls", name: "Check or correct judgement calls before import", since: BEFORE, guide: { id: "financial", heading: "Check judgement calls before import" }, tour: { area: "financial", step: "Calls the reader made" }, files: ["features/financial/components/JudgementCalls.tsx"], terms: ["Judgement calls"] },
  { id: "compare-statements", name: "Compare two statements side by side", since: BEFORE, guide: { id: "financial", heading: "Compare two statements side by side" }, tour: { area: "financial", step: "Two statements side by side" }, files: ["features/financial/components/StatementCompareView.tsx"], terms: ["Agrees and Differs", "May be a copy of"] },
  { id: "held-copies", name: "Held copies wait for a decision", since: BEFORE, guide: { id: "financial", heading: "Decide on held copies in the review queue" }, tour: { area: "financial", step: "Statements to check" }, files: ["features/financial/components/ReviewQueuePanel.tsx"], terms: ["May be a copy of"] },
]
