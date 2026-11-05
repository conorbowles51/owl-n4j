import { beforeEach, expect, it } from "vitest"
import { clearSessionMark, markSignedIn, sessionMark } from "./session-mark"

beforeEach(() => localStorage.clear())

it("is empty when signed out and changes at each sign-in", () => {
  expect(sessionMark()).toBeNull()
  markSignedIn()
  const first = sessionMark()
  markSignedIn()
  expect(first).toBeTruthy()
  expect(sessionMark()).not.toBe(first)
  clearSessionMark()
  expect(sessionMark()).toBeNull()
})

it("carries over a browser signed in by an earlier release and removes its token", () => {
  localStorage.setItem("authToken", "header.claims.signature")
  const mark = sessionMark()
  expect(mark).toBeTruthy()
  expect(mark).not.toContain("signature")
  expect(localStorage.getItem("authToken")).toBeNull()
  expect(sessionMark()).toBe(mark)
})
