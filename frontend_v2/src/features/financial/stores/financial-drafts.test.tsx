import { renderHook, act } from "@testing-library/react"
import { beforeEach, expect, it } from "vitest"
import { useFinancialDraft, useFinancialDraftStore } from "./financial-drafts"
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
