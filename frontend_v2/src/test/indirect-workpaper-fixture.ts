import type {
  CaseworkEntry,
  CaseworkLink,
} from "@/features/workspace/casework-api"
import type {
  IndirectCatalog,
  IndirectRequest,
} from "@/features/financial/lib/indirect-review"

export async function savedIndirectFixture(snapshot = true) {
  const caseId = "10000000-0000-4000-8000-000000000001"
  const fileId = "10000000-0000-4000-8000-000000000002"
  const catalog: IndirectCatalog = {
    case_id: caseId,
    reference: "https://www.irs.gov/irm/part9/irm_09-005-009",
    methods: [
      {
        id: "cash_t",
        label: "Cash-T",
        reference_section: "9.5.9.8.4",
        terms: [
          { id: "uses", label: "Cash used", sign: 1, signed: false },
          { id: "sources", label: "Cash available", sign: -1, signed: false },
        ],
      },
    ],
    requirements: [{ id: "opening", label: "Opening cash checked" }],
  }
  const reference = {
    basis: "Compared against the original",
    source_file_id: fileId,
    source_location: "Page 2",
  }
  const inputs: IndirectRequest = {
    method: "cash_t",
    subject: "Synthetic saved workpaper",
    currency: "GBP",
    start_date: "2026-01-01",
    end_date: "2026-12-31",
    entries: {
      uses: { ...reference, amount_minor: "10000" },
      sources: { ...reference, amount_minor: "6000" },
    },
    requirements: { opening: { ...reference, status: "reviewed" } },
  }
  const value = {
    schema: "loupe.financial.indirect_review/1",
    case_id: caseId,
    applied: false,
    reference: catalog.reference,
    reference_section: "9.5.9.8.4",
    inputs,
    method_label: "Cash-T",
    lines: catalog.methods[0].terms.map((term) => ({
      id: term.id,
      label: term.label,
      sign: term.sign,
      ...inputs.entries[term.id],
    })),
    sources: [
      {
        id: fileId,
        case_id: caseId,
        filename: "Synthetic.pdf",
        sha256: "a".repeat(64),
      },
    ],
    missing: [],
    review_fields_complete: true,
    difference_minor: "4000",
    limitation: "The result depends on the supplied amounts.",
  }
  const scenario_json = JSON.stringify(value)
  const bytes = new TextEncoder().encode(scenario_json)
  const scenario_sha256 = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  const envelope = {
    case_id: caseId,
    applied: false as const,
    scenario_json,
    scenario_sha256,
    scenario_byte_count: bytes.length,
  }
  const link: CaseworkLink = {
    id: "saved-link",
    case_id: caseId,
    entry_id: "saved-note",
    target_type: "evidence",
    target_id: fileId,
    target_label: "Synthetic.pdf",
    relationship: "context",
    source_anchor: { workpaper_sha256: scenario_sha256 },
    metadata: {
      schema: "loupe.financial.indirect_workpaper/1",
      envelope,
      ...(snapshot ? { catalog } : {}),
    },
  }
  const entry: CaseworkEntry = {
    id: "saved-note",
    case_id: caseId,
    entry_type: "note",
    title: "Saved cash comparison",
    body: "Investigator explanation",
    tags: ["financial", "indirect-review"],
    review_state: "accepted",
    version: 1,
    migration_metadata: {},
    needs_migration_review: false,
    links: [link],
  }
  return { caseId, fileId, catalog, inputs, value, envelope, link, entry }
}
