import { beforeEach, expect, it } from "vitest"
import { useInvestigationScopeStore } from "./investigation-scope"

beforeEach(() => useInvestigationScopeStore.getState().reset())
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
