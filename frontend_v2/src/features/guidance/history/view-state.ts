import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { useTimelineStore } from "@/features/timeline/stores/timeline.store"
import { useFinancialDraftStore } from "@/features/financial/stores/financial-drafts"
import { useInvestigationScopeStore } from "@/features/financial/stores/investigation-scope"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { StepItem } from "../api"
import { useDocumentStep, type DocumentStep } from "./document-step"

/**
 * What a step keeps (lx-guide I): the address, plus the view state the address does not hold: the selected item,
 * filters, sort, date range, open panel, the open document and its page, and the scroll position as the key of the
 * first row in view (never an index: lists are virtualised and change as rows arrive).
 */
export interface ViewState {
  scrollKey?: string
  panel?: { collapsed: boolean; tab: string }
  financial?: { drafts: Record<string, unknown>; scope: unknown }
  graph?: { selected: string[]; search: string; mode: string; types: string[] | null; hidden: string[]; subgraph: string[] }
  timeline?: { types: string[]; entities: string[]; range: { start: string | null; end: string | null }; search: string; event: string | null }
  document?: DocumentStep
}

export interface Snapshot {
  screen: string
  path: string
  state: ViewState
  item: StepItem | null
  name: string
}

const SCREENS: Record<string, string> = {
  workspace: "Case home",
  evidence: "Evidence",
  graph: "Graph",
  timeline: "Timeline",
  map: "Map",
  table: "Table",
  financial: "Financial",
  phones: "Phones",
  conversations: "Conversations",
  agent: "Agent",
  chat: "Chat",
  reports: "Reports",
  dossiers: "Dossiers",
  search: "Search",
  settings: "Case settings",
  "keyword-lists": "Keyword lists",
  "phone-analyses": "Phone analyses",
  "phone-patterns": "Phone patterns",
  "phone-money": "Money in messages",
  records: "Record",
}

const FINANCIAL_VIEWS: Record<string, string> = {
  overview: "Financial overview",
  "follow-money": "Follow the money",
  findings: "Financial findings",
  patterns: "Payment patterns",
  "case-context": "Case context",
  ledger: "Ledger",
  statements: "Statements",
  quarantine: "Set-aside lines",
  runs: "Readings",
  decisions: "Decisions",
  transactions: "Transactions",
  counterparties: "Counterparties",
  trends: "Trends",
  tracing: "Tracing",
}

/** The screen a case address is on: its id (for the backend) and its plain name. */
export function screenOf(pathname: string): { screen: string; label: string } {
  const first = /^\/cases\/[^/]+\/?([^/?#]*)/.exec(pathname)?.[1] || "workspace"
  const screen = first.startsWith("phone-analyses") ? "phone-analyses" : first
  const id = screen.toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 40) || "case"
  return { screen: id, label: SCREENS[screen] ?? screen.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase()) }
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
/** "Nov 2022", or "Nov 2022 to Feb 2023"; null when there is no range. */
export function rangeWords(start?: string | null, end?: string | null): string | null {
  const m = (d?: string | null) => {
    const x = /^(\d{4})-(\d{2})/.exec(d ?? "")
    return x ? `${MONTHS[Number(x[2]) - 1]} ${x[1]}` : null
  }
  const a = m(start)
  const b = m(end)
  if (a && b) return a === b ? a : `${a} to ${b}`
  return a ? `from ${a}` : b ? `to ${b}` : null
}

/**
 * The step's name, from what is on screen: "Transactions · BBVA 0110280038 · Nov 2022",
 * "Graph · Jose Alejandro Reyes Zeind", "Statement page 2 of 6 · 11 ARRENDO BBVA USD NOV 2022.pdf".
 */
export function stepName(parts: {
  pathname: string
  search: string
  state: ViewState
  label: (id: string) => string | null
}): string {
  const { pathname, search, state, label } = parts
  const params = new URLSearchParams(search)
  const doc = state.document
  if (doc?.evidenceId) {
    const page = doc.page ? `page ${doc.page}${doc.pages ? ` of ${doc.pages}` : ""}` : null
    const kind = /statement|bank|\.pdf$/i.test(doc.name ?? "") && pathname.includes("/financial") ? "Statement" : "Document"
    return [page ? `${kind} ${page}` : kind, doc.name || label(doc.evidenceId) || "a file"].join(" · ")
  }
  const { label: screenLabel } = screenOf(pathname)
  const out: string[] = []
  if (screenLabel === "Financial") {
    out.push(FINANCIAL_VIEWS[params.get("view") ?? ""] ?? "Financial")
    const scope = state.financial?.scope as { accountId?: string; accountHolders?: string[]; startDate?: string; endDate?: string } | undefined
    const account = scope?.accountId ? label(scope.accountId) : scope?.accountHolders?.[0] ?? null
    if (account) out.push(account)
    const range = rangeWords(scope?.startDate, scope?.endDate)
    if (range) out.push(range)
    const typed = Object.values(state.financial?.drafts ?? {}).find(
      (v): v is { search: string } => !!v && typeof v === "object" && typeof (v as { search?: unknown }).search === "string" && !!(v as { search: string }).search.trim()
    )
    if (typed) out.push(`"${typed.search.trim().slice(0, 40)}"`)
    const payment = params.get("payment")
    if (payment) out.push(label(payment) ?? "one payment")
  } else if (screenLabel === "Graph" || screenLabel === "Map") {
    out.push(screenLabel)
    const sel = state.graph?.selected ?? []
    if (sel.length === 1) out.push(label(sel[0]) ?? "one item selected")
    else if (sel.length > 1) out.push(`${sel.length.toLocaleString("en-US")} selected`)
    if (state.graph?.search) out.push(`"${state.graph.search}"`)
  } else if (screenLabel === "Timeline") {
    out.push("Timeline")
    const range = rangeWords(state.timeline?.range.start, state.timeline?.range.end)
    if (range) out.push(range)
    if (state.timeline?.event) out.push(label(state.timeline.event) ?? "one event")
    if (state.timeline?.search) out.push(`"${state.timeline.search}"`)
  } else if (screenLabel === "Evidence") {
    out.push("Evidence")
    const file = params.get("file")
    if (file) out.push(label(file) ?? "one file")
  } else if (screenLabel === "Case home") {
    const view = params.get("view")
    out.push(view === "casework" ? "Case work" : view ? view.replace(/^./, (c) => c.toUpperCase()) : "Case home")
    const entry = params.get("entry")
    if (entry) out.push(label(entry) ?? "one entry")
  } else {
    out.push(screenLabel)
    const tail = decodeURIComponent(pathname.split("/").slice(4).join(" · ")).replace(/-/g, " ")
    if (tail) out.push(tail.slice(0, 80))
  }
  return out.join(" · ")
}

/** The parts of a state that decide whether a change starts a new step; scroll and panel never do. */
export function meaningKey(s: Pick<Snapshot, "path" | "state" | "item">): string {
  const rest: ViewState = { ...s.state }
  delete rest.scrollKey
  delete rest.panel
  const doc = rest.document ? { evidenceId: rest.document.evidenceId } : undefined
  return JSON.stringify([s.path, s.item?.id ?? null, { ...rest, document: doc }])
}

/**
 * Whether the next snapshot is a tiny change to the last step (merge into it) or a new step. New screen, new item,
 * new filter applied: a new step. Scroll, a panel, the page of the same document, or a filter typed within
 * `typingMs` of the last change: the same step.
 */
export function mergesInto(last: Snapshot | null, next: Snapshot, msSinceLast: number, typingMs = 2500): boolean {
  if (!last) return false
  if (last.screen !== next.screen || (last.item?.id ?? null) !== (next.item?.id ?? null)) return false
  if (meaningKey(last) === meaningKey(next)) return true
  const pathOnly = (p: string) => p.split("?")[0]
  if (pathOnly(last.path) !== pathOnly(next.path)) return false
  return msSinceLast < typingMs && textOnly(last, next)
}

/** Only free-text search fields differ (typing in a filter box). */
function textOnly(a: Snapshot, b: Snapshot): boolean {
  const strip = (s: Snapshot) => {
    const st = JSON.parse(JSON.stringify(s.state)) as ViewState
    delete st.scrollKey
    delete st.panel
    if (st.graph) st.graph.search = ""
    if (st.timeline) st.timeline.search = ""
    if (st.financial) {
      for (const v of Object.values(st.financial.drafts)) if (v && typeof v === "object" && "search" in v) (v as { search: string }).search = ""
    }
    if (st.document) st.document = { ...st.document, page: 0 }
    const params = new URLSearchParams(s.path.split("?")[1] ?? "")
    params.delete("q")
    params.delete("search")
    return JSON.stringify([s.path.split("?")[0], params.toString(), st])
  }
  return strip(a) === strip(b)
}

// --- reading and applying the live stores ----------------------------------------------------------------------

const owner = () => {
  const u = useAuthStore.getState().user
  return u?.id || u?.username || "anonymous"
}
const scopeKey = (caseId: string) => {
  const u = useAuthStore.getState().user
  const o = u?.id || u?.username
  return o ? JSON.stringify([o, caseId]) : caseId
}

/** The key of the first row in view in the main content, or undefined. */
export function firstRowInView(root: ParentNode = document): string | undefined {
  const main = (root as Document).querySelector?.("main") ?? null
  const top = main ? main.getBoundingClientRect().top : 0
  for (const el of Array.from((main ?? root).querySelectorAll<HTMLElement>("[data-row-key]"))) {
    const r = el.getBoundingClientRect()
    if (r.height > 0 && r.bottom > top + 4) return el.getAttribute("data-row-key") ?? undefined
  }
  return undefined
}

export function readState(caseId: string, pathname: string): ViewState {
  const { screen } = screenOf(pathname)
  const ui = useUIStore.getState()
  const state: ViewState = { panel: { collapsed: ui.graphPanelCollapsed, tab: String(ui.graphPanelTab) } }
  const scroll = firstRowInView()
  if (scroll) state.scrollKey = scroll
  if (screen === "financial") {
    const prefix = `${owner()}:${caseId}:`
    const drafts: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(useFinancialDraftStore.getState().drafts)) if (k.startsWith(prefix)) drafts[k.slice(prefix.length)] = v
    state.financial = { drafts, scope: useInvestigationScopeStore.getState().scopes[scopeKey(caseId)] ?? {} }
  }
  if (screen === "graph" || screen === "map" || screen === "table") {
    const g = useGraphStore.getState()
    state.graph = {
      selected: [...g.selectedNodeKeys].slice(0, 200),
      search: g.appliedSearchQuery,
      mode: g.searchMode,
      types: g.selectedEntityTypes ? [...g.selectedEntityTypes] : null,
      hidden: [...g.hiddenNodeKeys].slice(0, 200),
      subgraph: [...g.subgraphNodeKeys].slice(0, 200),
    }
  }
  if (screen === "timeline") {
    const t = useTimelineStore.getState()
    state.timeline = {
      types: [...t.selectedTypes],
      entities: [...t.selectedEntityKeys].slice(0, 200),
      range: t.dateRange,
      search: t.searchTerm,
      event: t.selectedEventKey,
    }
  }
  const doc = useDocumentStep.getState().open
  if (doc) state.document = doc
  return state
}

/** The selected item a step is about, for "deleted or merged" checks on return. */
export function itemOf(pathname: string, search: string, state: ViewState, label: (id: string) => string | null): StepItem | null {
  const params = new URLSearchParams(search)
  const pick = (kind: string, id: string | null | undefined): StepItem | null =>
    id ? { kind, id, ...(label(id) ? { label: label(id)! } : {}) } : null
  if (state.document?.evidenceId) return pick("evidence", state.document.evidenceId)
  return (
    pick("financial_transaction", params.get("payment")) ??
    pick("evidence", params.get("file")) ??
    pick("entry", params.get("entry")) ??
    (state.graph?.selected.length === 1 ? pick("graph_entity", state.graph.selected[0]) : null) ??
    pick("timeline_event", state.timeline?.event) ??
    (pathname.includes("/records/") ? pick("phone_record", decodeURIComponent(pathname.split("/records/")[1] ?? "")) : null)
  )
}

/** Puts the stores back as the step had them, before its screen mounts. */
export function applyState(caseId: string, state: ViewState): void {
  if (state.panel) useUIStore.setState({ graphPanelCollapsed: state.panel.collapsed })
  if (state.financial) {
    const prefix = `${owner()}:${caseId}:`
    const store = useFinancialDraftStore.getState()
    for (const [k, v] of Object.entries(state.financial.drafts)) store.put(prefix + k, v)
    useInvestigationScopeStore.getState().apply(caseId, (state.financial.scope ?? {}) as Parameters<ReturnType<typeof useInvestigationScopeStore.getState>["apply"]>[1])
  }
  if (state.graph) {
    useGraphStore.setState({
      selectedNodeKeys: new Set(state.graph.selected),
      appliedSearchQuery: state.graph.search,
      searchDraft: state.graph.search,
      searchMode: state.graph.mode as "filter" | "search",
      selectedEntityTypes: state.graph.types ? new Set(state.graph.types) : null,
      hiddenNodeKeys: new Set(state.graph.hidden),
      subgraphNodeKeys: new Set(state.graph.subgraph),
    })
  }
  if (state.timeline) {
    useTimelineStore.setState({
      selectedTypes: new Set(state.timeline.types),
      selectedEntityKeys: new Set(state.timeline.entities),
      dateRange: state.timeline.range,
      searchTerm: state.timeline.search,
      selectedEventKey: state.timeline.event,
      scrollToEventKey: state.timeline.event,
    })
  }
  useDocumentStep.getState().request(state.document ?? null)
}

export { labelFromCache } from "../label"
