import { ACCESS_REFUSED_EVENT } from "./access-refused"
import { apiErrorMessage } from "./api-error-message"
import {
  ACCEPT_HEADER,
  acceptsUpdating,
  nextRequestNumber,
  noteOwnWrite,
  noteViewAnswer,
  updatingAsOf,
} from "./financial-view-updates"

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
  const { body, timeout, signal: callerSignal, onViewAnswer, ...init } = options

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

    if (onViewAnswer) {
      // Not asked to accept updating (just after this tab wrote): the answer is computed, so current.
      onViewAnswer(marksUpdating ? updatingAsOf(response) : undefined)
    } else if (marksUpdating) {
      noteViewAnswer(endpoint, updatingAsOf(response), requestNumber)
    }
    const method = (init.method ?? "GET").toUpperCase()
    if (response.ok && method !== "GET" && method !== "HEAD") noteOwnWrite()

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
      throw new ApiError(message, response.status, errorData)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return (await response.json()) as T
  } finally {
    inFlight -= 1
    clearTimeout(timeoutId)
    callerSignal?.removeEventListener("abort", abortFromCaller)
  }
}
