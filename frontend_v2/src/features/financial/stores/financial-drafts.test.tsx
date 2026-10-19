import { renderHook, act } from "@testing-library/react"
import { beforeEach, expect, it } from "vitest"
import {
  useFinancialDraft,
  useFinancialDraftStore,
  useFinancialOrderDraft,
} from "./financial-drafts"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  useAuthStore.setState({ user: null })
})
it("restores an unsaved draft after its form is unmounted and separates cases", () => {
  const first = renderHook(() =>
    useFinancialDraft("one", "note:transaction", "")
  )
  act(() => first.result.current[1]("Check the recipient"))
  first.unmount()
  const reopened = renderHook(() =>
    useFinancialDraft("one", "note:transaction", "")
  )
  expect(reopened.result.current[0]).toBe("Check the recipient")
  const other = renderHook(() =>
    useFinancialDraft("two", "note:transaction", "")
  )
  expect(other.result.current[0]).toBe("")
  act(() => reopened.result.current[2]())
  expect(reopened.result.current[0]).toBe("")
})
it("does not reveal another signed-in user's draft for the same case", () => {
  const owner = { id: "one", username: "one", name: "One", role: null }
  useAuthStore.setState({ user: owner })
  const draft = renderHook(() => useFinancialDraft("case", "observation", ""))
  act(() => draft.result.current[1]("Unfinished observation"))
  act(() =>
    useAuthStore.setState({ user: { ...owner, id: "two", username: "two" } })
  )
  expect(draft.result.current[0]).toBe("")
  act(() => draft.result.current[1]("Second user's work"))
  act(() => useAuthStore.setState({ user: owner }))
  expect(draft.result.current[0]).toBe("Unfinished observation")
})

it("retains order without retaining old readings or dropping new payments", () => {
  const original = [
    { id: "a", amount: "100" },
    { id: "b", amount: "200" },
  ]
  const first = renderHook(() =>
    useFinancialOrderDraft("case", "order", original, (r) => r.id)
  )
  act(() => first.result.current[1]((rows) => [...rows].reverse()))
  first.unmount()
  const changed = [
    { id: "a", amount: "101" },
    { id: "b", amount: "200" },
  ]
  const next = renderHook(() =>
    useFinancialOrderDraft("case", "order", changed, (r) => r.id)
  )
  expect(next.result.current[0]).toEqual([changed[1], changed[0]])
  next.unmount()
  const extended = [...changed, { id: "c", amount: "300" }]
  const fresh = renderHook(() =>
    useFinancialOrderDraft("case", "order", extended, (r) => r.id)
  )
  expect(fresh.result.current[0]).toEqual(extended)
  expect(
    JSON.stringify(useFinancialDraftStore.getState().drafts)
  ).not.toContain("amount")
})
