import { afterEach, expect, it, vi } from "vitest"
import { unzipSync, strFromU8 } from "fflate"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { findingReportBundle } from "./finding-report-bundle"
const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
afterEach(() => {
  vi.restoreAllMocks()
  api.mockReset()
})
const id = "11111111-1111-4111-8111-111111111111"
const entry = {
  id: "note",
  case_id: "case",
  version: 1,
  title: "Ask about payments",
  body: "Keep the original",
  entry_type: "note",
  tags: ["financial"],
  review_state: "accepted",
  migration_metadata: {},
  needs_migration_review: false,
  links: [
    {
      id: "link",
      entry_id: "note",
      case_id: "case",
      target_type: "evidence",
      target_id: id,
      target_label: "original.pdf",
      relationship: "context",
      source_anchor: { financial_transaction_ids: ["payment"] },
      metadata: {},
    },
  ],
} as CaseworkEntry
async function setup(change: Record<string, unknown> = {}) {
  const bytes = new TextEncoder().encode("%PDF-1.7 synthetic original bytes")
  const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map((n) => n.toString(16).padStart(2, "0"))
    .join("")
  api.mockImplementation(async (url) =>
    url.includes("/ledger/")
      ? {
          case_id: "case",
          transaction_id: "payment",
          evidence_file_id: id,
          sha256_at_ingestion: sha,
          recorded_digest_matches: true,
        }
      : {
          id,
          case_id: "case",
          original_filename: "../original.pdf",
          size: bytes.length,
          sha256: sha,
          ...change,
        }
  )
  const request = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(bytes))
  return { bytes, request }
}
it("packages the exact original bytes with a readable report and safe filenames", async () => {
  const { bytes } = await setup()
  const output = unzipSync(
    await findingReportBundle(entry, "case", new AbortController().signal)
  )
  const pdf = Object.keys(output).find((path) => path.endsWith(".pdf"))!
  expect(pdf).not.toContain("/../")
  expect([...output[pdf]]).toEqual([...bytes])
  expect(strFromU8(output["report.html"])).toContain(`href="${pdf}"`)
  expect(strFromU8(output["references.json"])).toContain('"entry_version": 1')
})
it("refuses a foreign case before fetching file bytes", async () => {
  const { request } = await setup({ case_id: "another" })
  await expect(
    findingReportBundle(entry, "case", new AbortController().signal)
  ).rejects.toThrow("another case")
  expect(request).not.toHaveBeenCalled()
})
it("refuses changed source bytes instead of delivering a partial package", async () => {
  const { request, bytes } = await setup()
  request.mockResolvedValue(new Response(new Uint8Array(bytes.length).fill(1)))
  await expect(
    findingReportBundle(entry, "case", new AbortController().signal)
  ).rejects.toThrow("differs from its recorded original")
})
it("refuses a payment citation pointing to a different file before downloading bytes", async () => {
  const { request } = await setup()
  const original = api.getMockImplementation()!
  api.mockImplementation(async (url) => {
    const result = await original(url)
    return url.includes("/ledger/")
      ? { ...result, evidence_file_id: "another-file" }
      : result
  })
  await expect(
    findingReportBundle(entry, "case", new AbortController().signal)
  ).rejects.toThrow("does not match its supporting PDF")
  expect(request).not.toHaveBeenCalled()
})
