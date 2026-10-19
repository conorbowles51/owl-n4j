import { act, renderHook } from "@testing-library/react"
import { beforeEach, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialStore } from "../stores/financial.store"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useOtherRecordsView } from "./use-other-records-view"

beforeEach(() => {
  useAuthStore.setState({ user: null })
  useFinancialStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
})
it("restores search, category/entity/date/amount filters, order, page and expanded records after refresh", () => {
  const first = renderHook(() => useOtherRecordsView("case-a"))
  const view = {
    searchQuery: "supplier",
    selectedCategories: new Set(["Review, priority"]),
    selectedTypes: new Set(["receipt"]),
    startDate: "2020-06-01",
    endDate: "2020-06-30",
    minAmount: "50",
    maxAmount: "125",
    entityFilter: { key: "entity-a", name: "Synthetic supplier" },
    sortColumns: [{ key: "amount", asc: true }],
    pageSize: 25,
    currentPage: 2,
    checkedKeys: new Set(["payment-a"]),
    lastClickedKey: "payment-a",
    expandedRowKeys: new Set(["payment-a"]),
  }
  act(() => useFinancialStore.setState(view))
  first.unmount()
  useFinancialStore.getState().reset()
  renderHook(() => useOtherRecordsView("case-a"))
  expect(useFinancialStore.getState()).toMatchObject(view)
  expect(
    JSON.parse(sessionStorage.getItem("loupe-financial-drafts")!).state.drafts[
      "anonymous:case-a:other-records-view"
    ].selectedCategories
  ).toEqual(["Review, priority"])
})
it("keeps private filter names and row selections separate across cases and signed-in users", () => {
  const current = renderHook(({ caseId }) => useOtherRecordsView(caseId), {
    initialProps: { caseId: "case-a" },
  })
  act(() =>
    useFinancialStore.setState({
      searchQuery: "private supplier",
      entityFilter: { key: "supplier-a", name: "Private supplier" },
      selectedCategories: new Set(["Sensitive review"]),
      checkedKeys: new Set(["row-a"]),
      expandedRowKeys: new Set(["row-a"]),
      currentPage: 2,
    })
  )
  current.rerender({ caseId: "case-b" })
  expect(useFinancialStore.getState()).toMatchObject({
    searchQuery: "",
    entityFilter: null,
    selectedCategories: new Set(),
    checkedKeys: new Set(),
    expandedRowKeys: new Set(),
    currentPage: 0,
  })
  act(() => useFinancialStore.getState().setSearchQuery("case b search"))
  current.rerender({ caseId: "case-a" })
  expect(useFinancialStore.getState().searchQuery).toBe("private supplier")
  act(() => useAuthStore.setState({ user: { id: "other-user" } as never }))
  expect(useFinancialStore.getState()).toMatchObject({
    searchQuery: "",
    entityFilter: null,
    selectedCategories: new Set(),
    checkedKeys: new Set(),
    expandedRowKeys: new Set(),
    currentPage: 0,
  })
  act(() => useAuthStore.setState({ user: null }))
  expect(useFinancialStore.getState().searchQuery).toBe("private supplier")
})
it("retains an explicit filter reset without discarding unrelated drafts", () => {
  useFinancialDraftStore
    .getState()
    .put("anonymous:case-a:some-note", "Keep this note")
  const first = renderHook(() => useOtherRecordsView("case-a"))
  act(() => useFinancialStore.getState().setSearchQuery("supplier"))
  act(() => useFinancialStore.getState().setMinAmount("50"))
  act(() => useFinancialStore.getState().resetFilters())
  first.unmount()
  renderHook(() => useOtherRecordsView("case-a"))
  expect(useFinancialStore.getState()).toMatchObject({
    searchQuery: "",
    minAmount: "",
    currentPage: 0,
  })
  expect(
    useFinancialDraftStore.getState().drafts["anonymous:case-a:some-note"]
  ).toBe("Keep this note")
})
it("does not save unrelated display changes or change the current dataset during hydration", () => {
  useFinancialStore.getState().setMode("intelligence")
  renderHook(() => useOtherRecordsView("case-a"))
  expect(useFinancialStore.getState().mode).toBe("intelligence")
  act(() => useFinancialStore.getState().setMainView("trends"))
  expect(useFinancialDraftStore.getState().drafts).toEqual({})
})
