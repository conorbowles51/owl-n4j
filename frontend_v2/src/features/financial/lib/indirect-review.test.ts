import { expect, it } from "vitest"
import {
  indirectMinor,
  verifyIndirectReview,
  type IndirectCatalog,
  type IndirectRequest,
} from "./indirect-review"
const caseId = "10000000-0000-4000-8000-000000000001",
  fileId = "10000000-0000-4000-8000-000000000002"
const catalog: IndirectCatalog = {
  case_id: caseId,
  reference: "https://www.irs.gov/irm/part9/irm_09-005-009",
  methods: [
    {
      id: "cash_t",
      label: "Cash-T",
      reference_section: "9.5.9.8.4",
      terms: [
        { id: "uses", label: "Uses", sign: 1, signed: false },
        { id: "sources", label: "Sources", sign: -1, signed: false },
      ],
    },
  ],
  requirements: [{ id: "opening", label: "Opening review" }],
}
const ref = {
  basis: "Synthetic assessment",
  source_file_id: fileId,
  source_location: "Page1",
}
const request: IndirectRequest = {
  method: "cash_t",
  currency: "GBP",
  subject: "Synthetic",
  start_date: "2026-01-01",
  end_date: "2026-12-31",
  entries: {
    uses: { ...ref, amount_minor: "9007199254740993" },
    sources: { ...ref, amount_minor: "9007199254740992" },
  },
  requirements: { opening: { ...ref, status: "reviewed" } },
}
const result = {
  schema: "loupe.financial.indirect_review/1",
  case_id: caseId,
  applied: false,
  reference: catalog.reference,
  reference_section: "9.5.9.8.4",
  inputs: request,
  method_label: "Cash-T",
  lines: catalog.methods[0].terms.map((t) => ({
    id: t.id,
    label: t.label,
    sign: t.sign,
    ...request.entries[t.id],
  })),
  sources: [
    {
      id: fileId,
      case_id: caseId,
      filename: "Synthetic.txt",
      sha256: "a".repeat(64),
    },
  ],
  missing: [],
  review_fields_complete: true,
  difference_minor: "1",
  limitation: "Conditional arithmetic",
}
async function envelope(value: unknown) {
  const scenario_json = JSON.stringify(value),
    bytes = new TextEncoder().encode(scenario_json),
    digest = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      (b) => b.toString(16).padStart(2, "0")
    ).join("")
  return {
    case_id: caseId,
    applied: false,
    scenario_json,
    scenario_sha256: digest,
    scenario_byte_count: bytes.length,
  }
}
it("verifies exact conditional arithmetic beyond Number precision", async () => {
  const verified = await verifyIndirectReview(
    await envelope(result),
    catalog,
    request
  )
  expect(verified.value.difference_minor).toBe("1")
})
it.each([
  { difference_minor: "0" },
  { review_fields_complete: false },
  { sources: [] },
  { missing: [{ kind: "review", id: "opening", label: "Opening review" }] },
])("rejects internally inconsistent recomputed captures %j", async (change) => {
  await expect(
    verifyIndirectReview(
      await envelope({ ...result, ...change }),
      catalog,
      request
    )
  ).rejects.toThrow()
})
it("withholds the result when the opening review remains unresolved", async () => {
  const changed = {
    ...request,
    requirements: { opening: { ...ref, status: "unresolved" as const } },
  }
  const value = {
    ...result,
    inputs: changed,
    missing: [{ kind: "review", id: "opening", label: "Opening review" }],
    review_fields_complete: false,
    difference_minor: null,
  }
  expect(
    (await verifyIndirectReview(await envelope(value), catalog, changed)).value
      .difference_minor
  ).toBeNull()
})
it("checks capture integrity and case isolation", async () => {
  const data = await envelope(result)
  await expect(
    verifyIndirectReview(
      { ...data, scenario_sha256: "0".repeat(64) },
      catalog,
      request
    )
  ).rejects.toThrow()
  await expect(
    verifyIndirectReview(data, { ...catalog, case_id: fileId }, request)
  ).rejects.toThrow()
})
it("parses only permitted signed currency amounts and keeps zero canonical", () => {
  expect(indirectMinor("-1.25", "GBP", true)).toBe("-125")
  expect(indirectMinor("-1.25", "GBP", false)).toBeNull()
  expect(indirectMinor("-0.00", "GBP", true)).toBe("0")
  expect(indirectMinor("1.234", "GBP", true)).toBeNull()
})
