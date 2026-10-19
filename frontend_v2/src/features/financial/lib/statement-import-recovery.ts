import { ApiError, fetchAPI } from "@/lib/api-client"

type Operation = { batch_id: string; status: string; outcomes: { message?: string }[] }
type Response = { receipt?: unknown; operation?: Operation | null; busy?: boolean; message?: string | null }

type Request = { rows: { excluded?: boolean }[] }

export function hasPendingStatementImport(key: string | null) {
  if (!key) return false
  try { return !!sessionStorage.getItem(key) } catch { return false }
}

/** The server accepted the import and is still saving it. This is not a failure. */
export class ImportStillSavingError extends Error {
  constructor() {
    super("Import accepted — still saving. Checking automatically; you can leave this screen. This will not repeat the import.")
    this.name = "ImportStillSavingError"
  }
}

const wait = (delay: number) => new Promise(resolve => window.setTimeout(resolve, delay))

/** Persist the submitted scope; recovery only reads receipts, never replays writes. */
export async function importWithReceiptRecovery<T extends Request>({
  endpoint, request, storageKey, recoverOnly, onChecking, onOperation, busyRetryDelays = [2000, 3000, 5000, 5000, 5000],
}: { endpoint: string; request: T; storageKey: string | null; recoverOnly?: boolean; onChecking: () => void; onOperation: (operation: Operation) => void; busyRetryDelays?: number[] }) {
  const [path, query] = endpoint.split("?")
  const url = (action: string) => `${path}/${action}${query ? `?${query}` : ""}`
  let submitted = request
  let pending = false
  if (storageKey) {
    try {
      const saved = sessionStorage.getItem(storageKey)
      if (saved) {
        const record = JSON.parse(saved)
        if (record.endpoint !== endpoint || !Array.isArray(record.request?.rows))
          throw Error("The pending import belongs to a different review. Reopen its saved statement.")
        submitted = record.request
        pending = true
      }
    } catch (error) {
      if (error instanceof SyntaxError) throw Error("The pending import could not be read. Check saved statements before importing again.")
      if (error instanceof Error && !(error instanceof DOMException)) throw error
    }
  }
  const clear = () => { if (storageKey) try { sessionStorage.removeItem(storageKey) } catch { /* Storage unavailable. */ } }
  let accepted: Operation | null = null
  const observe = (response: Response) => {
    if (response.operation) {
      accepted = response.operation
      onOperation(response.operation)
      if (response.operation.status === "needs_review" && !response.receipt)
        throw new ApiError(response.operation.outcomes.find(row => row.message)?.message || "The background import needs review. Open its processing batch.", 409)
    }
  }
  const wrap = (result: unknown) => ({ result, expectedCount: submitted.rows.filter(row => !row.excluded).length, clear })
  if (!pending && !recoverOnly) {
    if (storageKey) try { sessionStorage.setItem(storageKey, JSON.stringify({ endpoint, request: submitted })) } catch { /* In-tab recovery still works. */ }
    // A busy answer is definite: the server wrote nothing while another save
    // held this statement, so the same submission is repeated, never doubled.
    for (let attempt = 0; attempt <= busyRetryDelays.length; attempt++) {
      if (attempt) await wait(busyRetryDelays[attempt - 1])
      try {
        const response = await fetchAPI<Response>(url("queue-import"), { method: "POST", body: submitted, timeout: 30000 })
        if (response.busy && !response.operation && !response.receipt) {
          if (attempt === busyRetryDelays.length) {
            clear()
            throw new ApiError("Another save is still using this statement. Nothing was imported; choose Import again in a moment.", 409)
          }
          continue
        }
        observe(response)
        if (response.receipt) return wrap(response.receipt)
      } catch (error) {
        // A definite validation/access rejection does not leave a write uncertain.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408) {
          clear()
          throw error
        }
      }
      break
    }
  } else if (!pending) {
    throw Error("No pending import was found. Reopen the statement to check its saved result.")
  }
  onChecking()
  for (const delay of [0, 1000, 2000, 4000, 8000, 8000]) {
    if (delay) await wait(delay)
    try {
      const response = await fetchAPI<Response>(url("confirm-result"), {
        method: "POST", body: submitted, timeout: 10000,
      })
      observe(response)
      if (response.receipt) return wrap(response.receipt)
    } catch (error) {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408) throw error
    }
  }
  if ((accepted as Operation | null)?.status === "in_progress") throw new ImportStillSavingError()
  throw Error("The import has not returned a final receipt yet. Accepted jobs continue in the background; your submitted review is kept. Use Check saved result to check again; this will not repeat the import.")
}
