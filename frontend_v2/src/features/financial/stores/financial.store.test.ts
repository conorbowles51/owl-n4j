import { beforeEach, describe, expect, it } from "vitest"

import { useFinancialStore } from "./financial.store"

const KEY = "owl-financial-store"

function stored() {
  const raw = localStorage.getItem(KEY)
  return raw ? (JSON.parse(raw) as { state: Record<string, unknown> }) : null
}

describe("financial store, persisted tab", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
  })

  it("starts on transactions", () => {
    expect(useFinancialStore.getState().mainView).toBe("transactions")
  })

  it("holds a chosen tab for the visit", () => {
    useFinancialStore.getState().setMainView("trends")
    expect(useFinancialStore.getState().mainView).toBe("trends")
  })

  it("never writes the tab choice to the browser", () => {
    useFinancialStore.getState().setMainView("counterparties")

    const state = stored()?.state
    expect(state).toBeTruthy()
    expect(state).not.toHaveProperty("mainView")
    expect(state).not.toHaveProperty("mode")
    // The rest of the persisted surface is untouched by this change.
    expect(state).toHaveProperty("pageSize")
    expect(state).toHaveProperty("sortColumns")
  })

  /**
   * The blob an older build left behind. `merge` has to discard the tab and
   * keep everything else, or fixing the landing tab would cost the user their
   * page size and sort.
   */
  it("discards a tab left by an older build and keeps the rest", () => {
    const merge = (
      useFinancialStore.persist.getOptions() as {
        merge?: (persisted: unknown, current: unknown) => Record<string, unknown>
      }
    ).merge

    expect(merge).toBeTypeOf("function")

    const merged = merge!(
      { mainView: "transactions", pageSize: 200, mode: "intelligence" },
      useFinancialStore.getState()
    )

    expect(merged.mainView).toBe("transactions")
    expect(merged.pageSize).toBe(200)
    expect(merged.mode).toBe("transactions")
  })
})
