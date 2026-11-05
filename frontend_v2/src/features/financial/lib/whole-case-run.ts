import { useCallback, useRef, useState } from "react"
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { sha256Hex } from "@/lib/browser-crypto"
import { candidateUrl } from "./candidate-contract"

export type WholeCaseKind = "transfers" | "timeline" | "patterns" | "trace" | "pdf" | "export"

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
  privilege_marking?: string
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

export { isPdfSizeRefusal, isSizeRefusal, isTraceSizeRefusal, opensWholeCaseRun } from "./run-refusals"

function runUrl(id: string, caseId: string, rest = "") {
  return candidateUrl(`whole-case-runs/${encodeURIComponent(id)}${rest}`, caseId)
}

/** Starts the run (or joins the one for the same inputs) and follows it until it finishes or stops. */
export function useWholeCaseRun<Summary>(
  caseId: string,
  request: WholeCaseRequest | Record<string, unknown>,
  path = "whole-case-runs",
  enabled = true
) {
  const client = useQueryClient()
  // Each set of inputs has its own run: new inputs start or join theirs and never read the run of the last ones.
  const known = useRef(new Map<string, string>())
  const key = ["whole-case-run", caseId, JSON.stringify(request)]
  const identity = key.join("|")
  const query = useQuery({
    queryKey: key,
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    queryFn: async () => {
      const id = known.current.get(identity)
      const run = id
        ? await fetchAPI<WholeCaseRun<Summary>>(runUrl(id, caseId), {
            read: true,
          })
        : await fetchAPI<WholeCaseRun<Summary>>(
            candidateUrl(path, caseId),
            { method: "POST", body: request, read: true }
          )
      known.current.set(identity, run.id)
      return run
    },
    refetchInterval: (q) =>
      q.state.data?.status === "queued" || q.state.data?.status === "running"
        ? 2000
        : false,
  })
  const again = useCallback(() => {
    known.current.delete(identity)
    void client.resetQueries({ queryKey: key })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, identity])
  return { run: query.data, error: query.error, again }
}

/** A finished ledger export, as the run stated it. */
export interface ExportRunSummary {
  archive_bytes: number
  snapshot_bytes: number
  rows: number
  generated_at: string
  filename: string
  packet: unknown
  audit_events: { event_count: number; head_sha256: string; status: string } | null
  audit_parts: number
}

/**
 * A run a person starts: nothing starts on opening the page. The run's id stays in this browser, so leaving the page
 * and coming back finds the same run, whichever way it went.
 */
export function useStartedRun<Summary>(caseId: string, request: Record<string, unknown>, storageKey: string) {
  const [id, setId] = useState(() => localStorage.getItem(storageKey))
  const [startError, setStartError] = useState<Error | null>(null)
  const [starting, setStarting] = useState(false)
  const query = useQuery({
    queryKey: ["started-run", caseId, id],
    enabled: Boolean(id),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
    gcTime: 0,
    queryFn: async () => {
      try {
        return await fetchAPI<WholeCaseRun<Summary>>(runUrl(id!, caseId), { read: true })
      } catch (error) {
        // A run past its keeping time is gone: the page goes back to offering a new one.
        if ((error as { status?: number })?.status === 404) {
          localStorage.removeItem(storageKey)
          setId(null)
        }
        throw error
      }
    },
    refetchInterval: (q) => (q.state.data?.status === "queued" || q.state.data?.status === "running" ? 2000 : false),
  })
  const start = useCallback(
    async (fresh = false) => {
      setStarting(true)
      setStartError(null)
      try {
        const run = await fetchAPI<WholeCaseRun<Summary>>(candidateUrl("whole-case-runs", caseId), {
          method: "POST",
          body: { ...request, fresh },
          read: true,
        })
        localStorage.setItem(storageKey, run.id)
        setId(run.id)
        query.refetch().catch(() => undefined)
      } catch (error) {
        setStartError(error instanceof Error ? error : new Error("The export could not start."))
      } finally {
        setStarting(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [caseId, JSON.stringify(request), storageKey]
  )
  return { run: id ? query.data : undefined, startError, starting, start }
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
export type WholeCaseScenarioFigure = {
  currency: string
  posting_rows: number
  paired_transfers: number
  movement_count: number
  paired_amount_minor: string
  unpaired_credits_minor: string
  unpaired_debits_minor: string
  movement_volume_minor: string
}

export async function verifyWholeCaseScenario(
  raw: {
    case_id: string
    figures: WholeCaseScenarioFigure[]
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
    figures: WholeCaseScenarioFigure[]
  }
  const figures = (list: WholeCaseScenarioFigure[]) =>
    list.map((f) => [f.currency, f.posting_rows, f.paired_transfers, f.movement_count, f.paired_amount_minor, f.unpaired_credits_minor, f.unpaired_debits_minor, f.movement_volume_minor].join(":")).join(",")
  const names = (list: { debit_id: string; credit_id: string }[]) =>
    list.map((p) => `${p.debit_id}:${p.credit_id}`).join(",")
  if (
    saved.case_id !== caseId ||
    raw.case_id !== caseId ||
    saved.applied !== false ||
    saved.pairings_verified !== false ||
    names(saved.selected_pairs) !== names(pairs) ||
    figures(saved.figures) !== figures(raw.figures)
  )
    throw Error("Transfer report does not match the selected scope and assumptions.")
  return raw
}
