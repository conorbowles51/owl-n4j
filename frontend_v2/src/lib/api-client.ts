import { apiErrorMessage } from "./api-error-message"

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
}

export async function fetchAPI<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const token = localStorage.getItem("authToken")
  const { body, timeout, signal: callerSignal, ...init } = options

  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
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

      const detail = (errorData as { detail?: unknown })?.detail
      const message = apiErrorMessage(detail, response.status)
      throw new ApiError(message, response.status, errorData)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return (await response.json()) as T
  } finally {
    clearTimeout(timeoutId)
    callerSignal?.removeEventListener("abort", abortFromCaller)
  }
}
