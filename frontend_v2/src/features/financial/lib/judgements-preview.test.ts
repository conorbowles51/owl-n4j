import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { previewJudgements } from "./judgements"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))

it("the preview sends the statement's file and holder, so the holder kept as printed shows before saving", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ items: [] })
  await previewJudgements("case-1", {
    statement_id: "k1", currency: "USD", reading_rows: [], review_rows: [], file_id: "file-1", holder: "ERICA HOPPER",
  })
  const [url, options] = vi.mocked(fetchAPI).mock.calls[0]
  expect(url).toBe("/api/financial/judgements/preview?case_id=case-1")
  expect((options as { body: Record<string, unknown> }).body).toMatchObject({ file_id: "file-1", holder: "ERICA HOPPER" })
})
