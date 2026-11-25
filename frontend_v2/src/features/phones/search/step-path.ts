import type { NextStep } from "./api"

/** Where the scope travels: the phone screens' own parameter names (ui/scope.ts SCOPE_PARAMS). */
export interface StepScope {
  phones: string[]
  from: string | null
  to: string | null
}

const c = (caseId: string) => `/cases/${encodeURIComponent(caseId)}`

function withScope(base: Record<string, string>, scope: StepScope, own: Record<string, string | null>) {
  const q = new URLSearchParams(base)
  // the step's own phones and dates win; otherwise the search's scope travels on
  const phones = own.phones ?? (scope.phones.length ? scope.phones.join(",") : null)
  const from = own.from ?? scope.from
  const to = own.to ?? scope.to
  if (phones) q.set("phones", phones)
  if (from) q.set("from", from)
  if (to) q.set("to", to)
  return q
}

/**
 * The screen a next step opens, with its people, phones and period filled in (COMMON rule 4). One place, so the
 * person, ask and corroborate screens being rebuilt (lx-phoneperson, lx-phoneask, lx-corroredo) change one line each.
 */
export function stepPath(caseId: string, step: NextStep, scope: StepScope, exact = false): string {
  const p = step.open.params
  const q = p.q ?? ""
  switch (step.open.screen) {
    case "person":
      // every phone: the person is opened across all of them, whatever this search's phone scope
      return `${c(caseId)}/conversations?${new URLSearchParams({ tab: "people", people: p.people ?? "" })}`
    case "conversations":
      return `${c(caseId)}/conversations?${withScope({ q, ...(p.deleted ? { deleted: p.deleted } : {}), ...(exact ? { exact: "1" } : {}) }, scope, {})}`
    case "timeline":
      return `${c(caseId)}/timeline?${withScope({}, scope, { phones: p.phones, from: p.from, to: p.to })}`
    case "ask":
      return `${c(caseId)}/agent?${new URLSearchParams({ question: `What do the phones say about “${q}”?` })}`
    case "corroborate":
      return `${c(caseId)}/search?${new URLSearchParams({ q, group: "documents", ...(exact ? { exact: "1" } : {}) })}`
    case "phones":
      return `${c(caseId)}/phones`
    case "keyword_list":
      return `${c(caseId)}/keyword-lists`
    default:
      return c(caseId)
  }
}

/** The corroborate step arrives after the first results; it takes its rank after the person and deleted steps. */
export function withElsewhere(steps: NextStep[], extra: NextStep | null): NextStep[] {
  if (!extra) return steps
  const at = steps.findIndex((s) => !["limits", "person", "deleted"].includes(s.id))
  const list = [...steps]
  list.splice(at < 0 ? list.length : at, 0, extra)
  return list.map((s, i) => ({ ...s, rank: i + 1 }))
}
