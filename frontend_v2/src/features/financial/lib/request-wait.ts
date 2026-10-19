import { useEffect, useState } from "react"

/** Whole seconds since `active` became true; 0 while inactive. */
export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!active) {
      setSeconds(0)
      return
    }
    const started = Date.now()
    setSeconds(0)
    const timer = setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000
    )
    return () => clearInterval(timer)
  }, [active])
  return seconds
}

export type RequestFailure = { message: string; retry: boolean }

/** Say why a request stopped. A timed-out or unreachable request is never
 * shown as an empty result; `retry` says a repeat is safe and worth offering. */
export function requestFailure(
  error: unknown,
  action: string,
  { writes = false }: { writes?: boolean } = {}
): RequestFailure {
  const name =
    error && typeof (error as { name?: unknown }).name === "string"
      ? (error as { name: string }).name
      : ""
  // ApiError carries the HTTP status (checked structurally, not by class).
  const status =
    error && typeof (error as { status?: unknown }).status === "number"
      ? (error as { status: number }).status
      : 0
  const outcome = writes
    ? "It may still finish on the server. Try again: repeating the same save applies it only once."
    : "Nothing was changed."
  if (name === "AbortError" || name === "TimeoutError" || status === 408)
    return {
      message: `${action} took longer than the 5-minute limit and was stopped. ${outcome} If it happens again, select fewer files.`,
      retry: true,
    }
  if (status === 502 || status === 503 || status === 504)
    return {
      message: `${action} did not finish: the server took too long to answer. ${outcome}`,
      retry: true,
    }
  if (
    error instanceof TypeError &&
    /fetch|network|load failed/i.test(error.message)
  )
    return {
      message: `${action} could not reach the server. ${outcome}`,
      retry: true,
    }
  return {
    message: error instanceof Error ? error.message : `${action} failed.`,
    retry: false,
  }
}
