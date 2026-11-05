import { useCallback, useRef } from "react"
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { sha256Hex } from "@/lib/browser-crypto"
import { candidateUrl } from "./candidate-contract"

export type WholeCaseKind = "transfers" | "timeline" | "patterns"

export interface WholeCaseRequest {
  kind: WholeCaseKind
  population: string
  start_date?: string
  end_date?: string
  account_id?: string
  account_ids?: string[]
  account_holders?: string[]
  tolerance_days?: number
  window_days?: number
  threshold_minor?: string
  threshold_currency?: string
  cross_account?: boolean
}

export interface WholeCaseRun<Summary = Record<string, unknown>> {
  id: string
  kind: WholeCaseKind
  status: "queued" | "running" | "completed" | "failed" | "stopped"
  phase: string
  step: number
  steps: number
  done: number
  total: number
  error?: string
  counts?: Record<string, number>
  summary?: Summary
  result_sha256?: string
  code_version?: string
  seconds?: number
  created_at: string
}

export interface WholeCasePage<Item> {
  total: number
  offset: number
  limit: number
  items: Item[]
}

/**
 * A workbench's answer above its size limit: the server's stated refusal, which a stored whole-case run replaces.
 * Other refusals (a date tolerance, a missing date) stay on the page as they are.
 */
export function isSizeRefusal(message: string | undefined) {
  return /^More than [0-9, ]+.*(match|share|comparisons|extensions)|^A threshold candidate contains more than/i.test(
    message ?? ""
  )
}

function runUrl(id: string, caseId: string, rest = "") {
  return candidateUrl(`whole-case-runs/${encodeURIComponent(id)}${rest}`, caseId)
}

/** Starts the run (or joins the one for the same inputs) and follows it until it finishes or stops. */
export function useWholeCaseRun<Summary>(
  caseId: string,
  request: WholeCaseRequest
) {
  const client = useQueryClient()
  const known = useRef<string | null>(null)
  const key = ["whole-case-run", caseId, JSON.stringify(request)]
  const query = useQuery({
    queryKey: key,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    queryFn: async () => {
      const run = known.current
        ? await fetchAPI<WholeCaseRun<Summary>>(runUrl(known.current, caseId), {
            read: true,
          })
        : await fetchAPI<WholeCaseRun<Summary>>(
            candidateUrl("whole-case-runs", caseId),
            { method: "POST", body: request, read: true }
          )
      known.current = run.id
      return run
    },
    refetchInterval: (q) =>
      q.state.data?.status === "queued" || q.state.data?.status === "running"
        ? 2000
        : false,
  })
  const again = useCallback(() => {
    known.current = null
    void client.resetQueries({ queryKey: key })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, key.join("|")])
  return { run: query.data, error: query.error, again }
}

export function useWholeCasePage<Item>(
  caseId: string,
  run: WholeCaseRun<unknown> | undefined,
  section: string,
  offset: number,
  limit: number,
  search = ""
) {
  return useQuery({
    queryKey: ["whole-case-page", caseId, run?.id, run?.result_sha256, section, offset, limit, search],
    enabled: run?.status === "completed",
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
    queryFn: () => {
      const query = new URLSearchParams({ offset: String(offset), limit: String(limit) })
      if (search.trim()) query.set("search", search.trim())
      return fetchAPI<WholeCasePage<Item>>(
        `${runUrl(run!.id, caseId, `/pages/${encodeURIComponent(section)}`)}&${query}`
      )
    },
  })
}

/** The whole stored list as a file: nothing is held in this page. */
export function wholeCaseFileUrl(caseId: string, id: string, name: string) {
  return runUrl(id, caseId, `/files/${encodeURIComponent(name)}`)
}

/** A stored comparison's scenario report: its bytes match its digest and it records exactly what was asked. */
export async function verifyWholeCaseScenario(
  raw: {
    case_id: string
    scenario_json: string
    scenario_sha256: string
    scenario_byte_count: number
  },
  caseId: string,
  pairs: { debit_id: string; credit_id: string }[]
) {
  const bytes = new TextEncoder().encode(raw.scenario_json)
  if (
    (await sha256Hex(bytes)) !== raw.scenario_sha256 ||
    bytes.length !== raw.scenario_byte_count
  )
    throw Error("Transfer report failed its integrity check.")
  const saved = JSON.parse(raw.scenario_json) as {
    case_id: string
    applied: boolean
    pairings_verified: boolean
    selected_pairs: { debit_id: string; credit_id: string }[]
  }
  const names = (list: { debit_id: string; credit_id: string }[]) =>
    list.map((p) => `${p.debit_id}:${p.credit_id}`).join(",")
  if (
    saved.case_id !== caseId ||
    raw.case_id !== caseId ||
    saved.applied !== false ||
    saved.pairings_verified !== false ||
    names(saved.selected_pairs) !== names(pairs)
  )
    throw Error("Transfer report does not match the selected scope and assumptions.")
  return raw
}
