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
  const { body, timeout, ...init } = options

  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json"
  }

  const controller = new AbortController()
  const timeoutMs = timeout ?? (endpoint.includes("/auth/") ? 10000 : 300000)
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(endpoint, {
      ...init,
      headers,
      body:
        body instanceof FormData
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

      if (response.status === 401) {
        localStorage.removeItem("authToken")
      }

      const detail = (errorData as { detail?: unknown })?.detail
      const message =
        typeof detail === "string"
          ? detail
          : detail
            ? JSON.stringify(detail)
            : `Request failed: ${response.status}`
      throw new ApiError(message, response.status, errorData)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return (await response.json()) as T
  } finally {
    clearTimeout(timeoutId)
  }
}
