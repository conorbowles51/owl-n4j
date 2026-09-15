import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { financialAPI } from "./api"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
beforeEach(() => vi.mocked(fetchAPI).mockReset())
it.each(["not stated", null])(
  "passes the exact unreadable or missing original %j",
  async (original) => {
    vi.mocked(fetchAPI).mockResolvedValue({
      success: true,
      key: "one",
      amount: 125.5,
    })
    await expect(
      financialAPI.updateAmount("one", {
        caseId: "case",
        newAmount: 125.5,
        correctionReason: "Checked",
        expectedRawAmount: original,
      })
    ).resolves.toMatchObject({ amount: 125.5 })
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/financial/transactions/one/amount",
      expect.objectContaining({
        body: expect.objectContaining({
          expected_raw_amount: original,
          expected_amount: undefined,
        }),
      })
    )
  }
)
it.each([
  undefined,
  { success: true, key: "another", amount: 125.5 },
  { success: true, key: "one", amount: 0 },
  { success: false, key: "one", amount: 125.5 },
])(
  "refuses a response that does not confirm this correction",
  async (response) => {
    vi.mocked(fetchAPI).mockResolvedValue(response)
    await expect(
      financialAPI.updateAmount("one", {
        caseId: "case",
        newAmount: 125.5,
        correctionReason: "Checked",
      })
    ).rejects.toThrow("not confirmed")
  }
)
