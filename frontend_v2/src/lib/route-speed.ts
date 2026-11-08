import { useLocation } from "react-router-dom"
import { useViewSpeed } from "@/features/financial/lib/page-speed"

/**
 * Every route of the app is timed like a Financial view: opening (LOAD) or switching to it (VIEW) until its
 * data is on screen, or how long the person waited before leaving (LEFT), with the browser's own figures.
 * Page names are fixed (backend services/request_speed.py APP_PAGES); the case id is sent as its own field.
 */

const CASE_ROUTES = new Set([
  "graph", "timeline", "map", "table", "financial", "dossiers", "evidence", "chat", "agent",
  "workspace", "reports", "settings", "phone-review", "phone-patterns", "conversations", "search",
  "keyword-lists",
])
/** Phone record types named in a page (backend PHONE_RECORD_TYPES); any other type is "other". */
export const PHONE_RECORD_TYPES = new Set([
  "messages", "calls", "contacts", "locations", "media", "apps", "web", "notes", "events", "accounts", "devices", "other",
  "conversations",
])
const PROTOTYPE_VIEWS = new Set(["summary", "conversations", "needs-a-decision"])

/** Phone pages below /cases/:id (07 4.13). Extraction ids and approach names are never part of the page name. */
function phonePage(rest: string[]): string | null {
  const [view, sub, kind, type] = rest
  if (view === "phones") {
    if (!sub) return "case/phones"
    if (!kind) return "case/phones/summary"
    // the list for a record type carries the report's type name, never part of a page name (03 section 7.5)
    if (kind === "records" && type && rest.length === 4) return `case/phones/records/${PHONE_RECORD_TYPES.has(type) ? type : "other"}`
    return null
  }
  if ((view === "phone-review" || view === "phone-patterns" || view === "phone-money") && rest.length === 1) return `case/${view}`
  if (view === "phone-analyses" && rest.length <= 2) return "case/phone-analyses"
  if (view === "phones-prototype" && rest.length <= 2) {
    const v = sub ?? "summary"
    return PROTOTYPE_VIEWS.has(v) ? `case/phones-prototype/${v}` : null
  }
  return null
}

const ADMIN_ROUTES = new Set(["ai-costs", "users", "profiles", "logs", "activity", "speed", "tasks", "updates", "phone-registry"])

/** The page name and case for a path (routes.tsx); the redirecting addresses are named after their target. */
export function routePage(pathname: string): { page: string | null; caseId: string | null } {
  const parts = pathname.replace(/\/+$/, "").split("/").filter(Boolean)
  if (parts.length === 0) return { page: "cases", caseId: null }
  const [first, second, third] = parts
  if (first === "login") return { page: null, caseId: null }
  if (first === "cases") {
    if (!second) return { page: "cases", caseId: null }
    if (!third) return { page: "case/workspace", caseId: second } // index redirects to workspace
    const phone = phonePage(parts.slice(2))
    if (phone) return { page: phone, caseId: second }
    // The text workbench for one evidence file; the file id is never part of the page name.
    if (third === "evidence" && parts.length === 5 && parts[4] === "text") return { page: "case/evidence/text", caseId: second }
    const view = third === "profiles" ? "dossiers" : third
    return { page: CASE_ROUTES.has(view) && parts.length === 3 ? `case/${view}` : "other", caseId: second }
  }
  if (first === "admin") {
    if (!second) return { page: "admin", caseId: null }
    if (second === "usage") return { page: "admin/ai-costs", caseId: null }
    return { page: ADMIN_ROUTES.has(second) && parts.length === 2 ? `admin/${second}` : "other", caseId: null }
  }
  if (first === "triage" && parts.length === 1) return { page: "triage", caseId: null }
  if (first === "settings") {
    if (parts.length === 1) return { page: "settings", caseId: null }
    if (second === "ai" && parts.length === 2) return { page: "settings/ai", caseId: null }
  }
  return { page: "other", caseId: null }
}

/** Mounted once, inside the signed-in layout. */
export function useRouteSpeed() {
  const { pathname } = useLocation()
  const { page, caseId } = routePage(pathname)
  useViewSpeed(caseId, page, "route")
}
