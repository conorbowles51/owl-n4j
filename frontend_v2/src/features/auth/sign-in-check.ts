import { authAPI } from "./api"
import type { User } from "./auth.types"

/**
 * The sign-in check (GET /api/auth/me) sent from main.tsx before React renders, then handed to ProtectedRoute,
 * which handles its answer exactly as it handles its own (setUser, sign-out on 401/403, retry on a failed
 * connection).
 *
 * Measured 4 Nov (A/B, signed in): starting a page's code at start-up sends dozens of script requests at once;
 * on plain http (6 connections per host) a sign-in check sent after them waited behind them (30 ms became
 * 0.7-1.7 s), and every request that needs the session waited with it. Sent first, it is never queued behind
 * the page's code; and it no longer waits for the shell's first render.
 */
let early: { token: string; answer: Promise<User> } | null = null

/** Sends the sign-in check now if someone is signed in; returns its answer, or null when signed out. */
export function startSignInCheck(): Promise<User> | null {
  const token = localStorage.getItem("authToken")
  if (!token) return null
  const answer = authAPI.me()
  answer.catch(() => {}) // ProtectedRoute reads the failure
  early = { token, answer }
  return answer
}

/** ProtectedRoute: the check already sent for this sign-in (once), or null to send its own. */
export function takeSignInCheck(token: string | null): Promise<User> | null {
  const sent = early
  early = null
  return sent && sent.token === token ? sent.answer : null
}
