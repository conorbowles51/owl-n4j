import { beforeEach, expect, it } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  useAnalysisPopulation,
  useInvestigationScope,
  useInvestigationScopeStore,
} from "./investigation-scope"

beforeEach(() => {
  useAuthStore.setState({ user: null })
  useInvestigationScopeStore.getState().reset()
})
it("retains each case's applied account and dates without carrying another case's scope", () => {
  const store = useInvestigationScopeStore.getState()
  store.apply("case-a", { accountId: "account-a", startDate: "2023-01-01" })
  store.apply("case-b", { endDate: "2024-01-01" })
  expect(useInvestigationScopeStore.getState().scopes["case-a"]).toEqual({
    accountId: "account-a",
    startDate: "2023-01-01",
  })
  expect(useInvestigationScopeStore.getState().scopes["case-b"]).toEqual({
    endDate: "2024-01-01",
  })
  store.apply("case-a", {})
  expect(useInvestigationScopeStore.getState().scopes["case-a"]).toEqual({})
  expect(useInvestigationScopeStore.getState().scopes["case-b"]).toEqual({
    endDate: "2024-01-01",
  })
})

it("rehydrates account, dates and population without sharing another user's scope", async () => {
  const owner = { id: "one", username: "one", name: "One", role: null }
  useAuthStore.setState({ user: owner })
  const hook = renderHook(() => ({
    scope: useInvestigationScope("case"),
    population: useAnalysisPopulation("case"),
  }))
  const scope = {
    accountId: "checking",
    startDate: "2020-07-01",
    endDate: "2020-07-31",
  }
  act(() => {
    hook.result.current.scope[1](scope)
    hook.result.current.population[1]("verified")
  })
  const saved = sessionStorage.getItem("loupe-investigation-scope")!
  act(() => useInvestigationScopeStore.getState().reset())
  sessionStorage.setItem("loupe-investigation-scope", saved)
  await act(() => useInvestigationScopeStore.persist.rehydrate())
  expect(hook.result.current.scope[0]).toEqual(scope)
  expect(hook.result.current.population[0]).toBe("verified")
  act(() => useAuthStore.setState({ user: { ...owner, id: "two" } }))
  expect(hook.result.current.scope[0]).toEqual({})
  expect(hook.result.current.population[0]).toBe("working")
  act(() => useAuthStore.setState({ user: owner }))
  expect(hook.result.current.scope[0]).toEqual(scope)
  expect(hook.result.current.population[0]).toBe("verified")
})
