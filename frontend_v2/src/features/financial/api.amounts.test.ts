import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { financialAPI } from "./api"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
beforeEach(() => vi.mocked(fetchAPI).mockReset())
it("passes the exact unreadable original and only confirms the requested record and amount", async () => {
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
      expectedRawAmount: "not stated",
    })
  ).resolves.toMatchObject({ amount: 125.5 })
  expect(fetchAPI).toHaveBeenCalledWith(
    "/api/financial/transactions/one/amount",
    expect.objectContaining({
      body: expect.objectContaining({
        expected_raw_amount: "not stated",
        expected_amount: undefined,
      }),
    })
  )
})
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
