import { ACCESS_REFUSED_EVENT } from "./access-refused"
import { apiErrorMessage } from "./api-error-message"
import {
  ACCEPT_HEADER,
  acceptsUpdating,
  nextRequestNumber,
  isOwnWrite,
  noteOwnWrite,
  noteViewAnswer,
  updatingAsOf,
} from "./financial-view-updates"
import { answerRequest, bodyLength, endRequest, readJSON, startRequest } from "./request-progress"

export class ApiError extends Error {
  status: number
  data?: unknown

  constructor(message: string, status: number, data?: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.data = data
  }
}

interface FetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown
  timeout?: number
  /**
   * Called with an updating answer's as-of time (or undefined when current) instead of recording it for the
   * page: the updating notice's own checks record a current answer only once the page has fetched it again.
   */
  onViewAnswer?: (asOf: string | undefined) => void
  /**
   * Only the answer's status and headers are wanted: a successful body is cancelled unread and undefined is
   * returned. The updating notice's checks use it, so each check does not download and parse a whole view (a
   * d5b330d1 ledger is 64 MB) only to read its headers.
   */
  headersOnly?: boolean
  /**
   * The request only reads, whatever its method (a POST carrying an id list or a query): it is not counted as
   * this tab's own write, so Financial's updating answers stay on (financial-view-updates isOwnWrite).
   */
  read?: boolean
}

let inFlight = 0

/** API requests started through fetchAPI that have not finished yet (the page-speed post waits for none). */
export function apiRequestsInFlight() {
  return inFlight
}

export async function fetchAPI<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const token = localStorage.getItem("authToken")
  const { body, timeout, signal: callerSignal, onViewAnswer, headersOnly, read, ...init } = options

  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  const marksUpdating = acceptsUpdating(endpoint, init.method)
  const requestNumber = marksUpdating ? nextRequestNumber() : 0
  if (marksUpdating) {
    headers[ACCEPT_HEADER] = "updating"
  }

  const rawBody = body instanceof FormData || body instanceof Blob
  if (body && !rawBody) {
    headers["Content-Type"] = "application/json"
  }

  const controller = new AbortController()
  const abortFromCaller = () => controller.abort(callerSignal?.reason)
  if (callerSignal?.aborted) abortFromCaller()
  else callerSignal?.addEventListener("abort", abortFromCaller, { once: true })
  const timeoutMs = timeout ?? (endpoint.includes("/auth/") ? 10000 : 300000)
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  inFlight += 1
  // Reads (GET, or any method flagged as a read) are recorded for the loading panel; writes and the page-speed
  // posts are not page loads.
  const counted = (read || (init.method ?? "GET").toUpperCase() === "GET") && !headersOnly
  const progressId = counted ? startRequest(endpoint) : 0
  let failure: string | null = "Stopped before an answer"

  try {
    const response = await fetch(endpoint, {
      ...init,
      headers,
      body: rawBody
        ? (body as BodyInit)
        : body
          ? JSON.stringify(body)
          : undefined,
      signal: controller.signal,
      credentials: "include",
    })
    if (counted) answerRequest(progressId, bodyLength(response))

    if (onViewAnswer) {
      // Not asked to accept updating (just after this tab wrote): the answer is computed, so current.
      onViewAnswer(marksUpdating ? updatingAsOf(response) : undefined)
    } else if (marksUpdating) {
      noteViewAnswer(endpoint, updatingAsOf(response), requestNumber)
    }
    if (response.ok && isOwnWrite(endpoint, init.method, read)) noteOwnWrite()

    if (!response.ok) {
      let errorData: unknown
      try {
        errorData = await response.json()
      } catch {
        // ignore parse errors
      }

      if (
        response.status === 401 &&
        localStorage.getItem("authToken") === token
      ) {
        localStorage.removeItem("authToken")
      }

      if (response.status === 401 || response.status === 403) {
        window.dispatchEvent(
          new CustomEvent(ACCESS_REFUSED_EVENT, { detail: endpoint })
        )
      }

      const detail = (errorData as { detail?: unknown })?.detail
      const message = apiErrorMessage(detail, response.status)
      failure = message
      throw new ApiError(message, response.status, errorData)
    }

    if (response.status === 204) {
      failure = null
      return undefined as T
    }

    if (headersOnly) {
      await response.body?.cancel().catch(() => undefined)
      failure = null
      return undefined as T
    }

    const value = counted ? await readJSON<T>(response, progressId) : ((await response.json()) as T)
    failure = null
    return value
  } catch (error) {
    if (failure === "Stopped before an answer" && error instanceof Error)
      failure = controller.signal.aborted && !callerSignal?.aborted ? "Took too long and was stopped" : error.message
    throw error
  } finally {
    // A read the caller cancelled (the person left, or React Query dropped it) is not a failure to show.
    if (counted) endRequest(progressId, callerSignal?.aborted ? null : failure)
    inFlight -= 1
    clearTimeout(timeoutId)
    callerSignal?.removeEventListener("abort", abortFromCaller)
  }
}
