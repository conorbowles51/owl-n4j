import { useLocation } from "react-router-dom"
import { useViewSpeed } from "@/features/financial/lib/page-speed"

/**
 * Every route of the app is timed like a Financial view: opening (LOAD) or switching to it (VIEW) until its
 * data is on screen, or how long the person waited before leaving (LEFT), with the browser's own figures.
 * Page names are fixed (backend services/request_speed.py APP_PAGES); the case id is sent as its own field.
 */

const CASE_ROUTES = new Set([
  "graph", "timeline", "map", "table", "financial", "cellebrite", "dossiers", "evidence", "chat", "agent",
  "workspace", "reports", "settings",
])
const ADMIN_ROUTES = new Set(["ai-costs", "users", "profiles", "logs", "activity", "speed", "tasks", "updates"])

/** The page name and case for a path (routes.tsx); the redirecting addresses are named after their target. */
export function routePage(pathname: string): { page: string | null; caseId: string | null } {
  const parts = pathname.replace(/\/+$/, "").split("/").filter(Boolean)
  if (parts.length === 0) return { page: "cases", caseId: null }
  const [first, second, third] = parts
  if (first === "login") return { page: null, caseId: null }
  if (first === "cases") {
    if (!second) return { page: "cases", caseId: null }
    if (!third) return { page: "case/workspace", caseId: second } // index redirects to workspace
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
