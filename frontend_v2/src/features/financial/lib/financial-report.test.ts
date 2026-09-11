import { afterEach, expect, it, vi } from "vitest"
import { strFromU8, unzipSync } from "fflate"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { sha256Hex } from "@/lib/browser-crypto"
import { savedIndirectFixture } from "@/test/indirect-workpaper-fixture"
import { paymentFixture } from "./payment-fixture.test-support"
import { traceFixture } from "./trace-fixture.test-support"
import { traceFindingLinks } from "./saved-trace"
import {
  prepareFinancialReport,
  notePaymentTotals,
  readFinancialReport,
  readSavedFinancialReport,
  reportSaveInput,
  financialReportDownload,
} from "./financial-report"

const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
afterEach(() => {
  vi.restoreAllMocks()
  api.mockReset()
})
const fileId = "11111111-1111-4111-8111-111111111111"
function note(id = "note"): CaseworkEntry {
  return {
    id,
    case_id: "case",
    title: `Observation ${id}`,
    body: "Why <script>bad()</script> & when?",
    entry_type: "note",
    tags: ["financial"],
    version: 1,
    review_state: "accepted",
    migration_metadata: {},
    needs_migration_review: false,
    links: [
      {
        id: `link-${id}`,
        entry_id: id,
        case_id: "case",
        target_type: "evidence",
        target_id: fileId,
        target_label: "source.pdf",
        relationship: "context",
        source_anchor: { financial_transaction_ids: [paymentFixture.key] },
        metadata: {
          schema: "loupe.financial.payment_selection/1",
          transactions: [structuredClone(paymentFixture)],
        },
      },
    ],
  }
}
const prepare = (notes: CaseworkEntry[]) =>
  prepareFinancialReport({
    caseId: notes[0].case_id,
    caseTitle: "Synthetic case",
    title: "Payments <review>",
    introduction: "Investigate & compare",
    notes,
  })
function saved(report: Awaited<ReturnType<typeof prepare>>): CaseworkEntry {
  const input = reportSaveInput(report)
  return {
    ...note("report"),
    ...input,
    links: input.links!.map((link, i) => ({
      ...link,
      id: `saved-${i}`,
      entry_id: "report",
      case_id: report.data.case_id,
      relationship: link.relationship!,
      metadata: link.metadata!,
      source_anchor: link.source_anchor!,
    })),
  }
}
it("keeps note order, escaped writing and exact per-note totals without adding overlapping findings", async () => {
  const a = note("first"),
    b = note("second")
  a.links.push({ ...structuredClone(a.links[0]), id: "duplicate-link" })
  const totals = notePaymentTotals(a)
  expect(totals.count).toBe(1)
  expect(totals.groups[0].credits).toBe(9007199254740993n)
  const report = await prepare([b, a])
  expect(report.data.notes.map((n) => n.id)).toEqual(["second", "first"])
  expect(report.html).toContain("&lt;script&gt;")
  expect(report.html).not.toContain("<script>")
  expect(report.html).toContain("Payments &lt;review&gt;")
  expect(report.html).toContain("must not be added together")
  expect(report.html).not.toContain("18014398509481986")
  expect(report.files).toHaveLength(1)
})
it("keeps different accounts and currencies separate and refuses conflicting saved payment copies", () => {
  const a = note()
  a.links[0].metadata.transactions = [
    paymentFixture,
    {
      ...paymentFixture,
      key: "two",
      account_id: "second-account",
      amount_minor: "200",
      direction: "debit",
    },
    { ...paymentFixture, key: "three", currency: "GBP", amount_minor: "300" },
  ]
  expect(notePaymentTotals(a).groups).toHaveLength(3)
  a.links[0].metadata.transactions = [
    paymentFixture,
    { ...paymentFixture, amount_minor: "1" },
  ]
  expect(() => notePaymentTotals(a)).toThrow("conflicting")
})
it("refuses foreign, unbound and duplicated notes and reports nested as findings", async () => {
  await expect(prepare([note(), note()])).rejects.toThrow("more than once")
  const foreign = note("foreign")
  foreign.case_id = "other"
  await expect(prepare([note(), foreign])).rejects.toThrow("another case")
  const missing = note()
  missing.links[0].source_anchor.financial_transaction_ids = []
  await expect(prepare([missing])).rejects.toThrow("supporting link")
  const nested = note()
  nested.tags.push("financial-report")
  await expect(prepare([nested])).rejects.toThrow("original findings")
})
it("reopens the saved note version after the original is edited and rejects changed report bytes or references", async () => {
  const original = note(),
    before = structuredClone(original),
    report = await prepare([original])
  const entry = saved(report)
  original.body = "Changed later"
  original.version++
  const reopened = await readSavedFinancialReport(entry, "case")
  expect(reopened.data.notes[0].body).toBe(before.body)
  expect(reopened.data.notes[0].version).toBe(1)
  await expect(
    readFinancialReport(
      { ...report.envelope, report_json: report.envelope.report_json + " " },
      "case"
    )
  ).rejects.toThrow("recorded contents")
  entry.links[0].source_anchor.note_version = 2
  await expect(readSavedFinancialReport(entry, "case")).rejects.toThrow(
    "attached notes"
  )
})
it("captures a legacy calculation definition without changing the original and reopens without the server", async () => {
  const f = await savedIndirectFixture(false),
    before = structuredClone(f.entry)
  api.mockResolvedValue(f.catalog)
  const report = await prepare([f.entry])
  expect(f.entry).toEqual(before)
  expect(api).toHaveBeenCalledTimes(1)
  api.mockRejectedValue(Error("Offline"))
  expect((await readFinancialReport(report.envelope, f.caseId)).html).toContain(
    "Calculated difference: 40.00 GBP"
  )
  expect(api).toHaveBeenCalledTimes(1)
  const changed = JSON.parse(report.envelope.report_json)
  delete changed.notes[0].links[0].metadata.catalog
  const report_json = JSON.stringify(changed),
    bytes = new TextEncoder().encode(report_json)
  await expect(
    readFinancialReport(
      {
        ...report.envelope,
        report_json,
        bytes: bytes.length,
        sha256: await sha256Hex(bytes),
      },
      f.caseId
    )
  ).rejects.toThrow("method definition")
})
it("includes saved tracing results and requires the original payment references", async () => {
  const trace = await traceFixture(),
    a = note()
  a.links = (await traceFindingLinks(trace)).map((link, i) => ({
    ...link,
    id: String(i),
    entry_id: a.id,
    case_id: a.case_id,
    relationship: link.relationship!,
    metadata: link.metadata!,
    source_anchor: link.source_anchor!,
  }))
  expect((await prepare([a])).html).toContain("Saved tracing calculation")
  a.links[0].source_anchor.financial_transaction_ids = []
  await expect(prepare([a])).rejects.toThrow("saved payment references")
})
it("downloads a report and recorded data without fetching any original files", async () => {
  const request = vi.spyOn(globalThis, "fetch"),
    report = await prepare([note()])
  const zip = unzipSync(
    await financialReportDownload(report, false, new AbortController().signal)
  )
  expect(Object.keys(zip).sort()).toEqual([
    "contents.json",
    "report.html",
    "saved-report.json",
  ])
  const manifest = JSON.parse(strFromU8(zip["contents.json"]))
  for (const member of manifest.members) {
    expect(zip[member.path].length).toBe(member.bytes)
    expect(await sha256Hex(zip[member.path])).toBe(member.sha256)
  }
  expect(request).not.toHaveBeenCalled()
  expect(api).not.toHaveBeenCalled()
})
it("includes a shared original PDF once and checks its bytes and payment references", async () => {
  const bytes = new TextEncoder().encode("%PDF-1.7 synthetic original"),
    sha256 = await sha256Hex(bytes)
  api.mockImplementation(async (url) =>
    url.includes("/ledger/")
      ? {
          case_id: "case",
          transaction_id: "payment",
          evidence_file_id: fileId,
          sha256_at_ingestion: sha256,
          recorded_digest_matches: true,
        }
      : {
          id: fileId,
          case_id: "case",
          original_filename: "source.pdf",
          size: bytes.length,
          sha256,
        }
  )
  const request = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(bytes))
  const report = await prepare([note("one"), note("two")])
  const zip = unzipSync(
    await financialReportDownload(report, true, new AbortController().signal)
  )
  expect(request).toHaveBeenCalledTimes(1)
  expect([...zip["statements/1-source.pdf"]]).toEqual([...bytes])
  expect(strFromU8(zip["report.html"])).toContain(
    'href="statements/1-source.pdf"'
  )
  expect(strFromU8(zip["report.html"])).not.toContain(
    "Original statement files and unrelated case records are not included"
  )
})
it("refuses a PDF replaced since a saved calculation was prepared", async () => {
  const f = await savedIndirectFixture(),
    report = await prepare([f.entry])
  api.mockResolvedValue({
    id: f.fileId,
    case_id: f.caseId,
    original_filename: "Synthetic.pdf",
    size: 20,
    sha256: "b".repeat(64),
  })
  const request = vi.spyOn(globalThis, "fetch")
  await expect(
    financialReportDownload(report, true, new AbortController().signal)
  ).rejects.toThrow("source recorded")
  expect(request).not.toHaveBeenCalled()
})
