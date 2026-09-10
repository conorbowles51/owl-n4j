import { describe, it, expect } from "vitest"
import {
  modelNominationPlans,
  pdfModelNomination,
} from "./pdf-model-nomination"
const id = "11111111-1111-4111-8111-111111111111"
const revision = "a".repeat(64)
it("retains captured provider identity separately and accepts older requests without transport metadata", () => {
  const original = raw()
  expect(pdfModelNomination.parse(original).result?.transport).toBeUndefined()
  const transport = {
    schema_version: "loupe.pdf_model_transport/1",
    status: "captured",
    request_arguments: { model: "requested" },
    request_arguments_sha256: revision,
    adapter_sha256: revision,
    response_metadata: { reported_model: "reported-revision" },
    limitation: "Synthetic metadata",
  }
  const parsed = pdfModelNomination.parse({
    ...original,
    result: { ...original.result, transport },
  })
  expect(
    parsed.result?.transport?.status === "captured" &&
      parsed.result.transport.response_metadata.reported_model
  ).toBe("reported-revision")
  expect(() =>
    pdfModelNomination.parse({
      ...original,
      result: {
        ...original.result,
        transport: { ...transport, adapter_sha256: "invalid" },
      },
    })
  ).toThrow()
})
const cells = (amountColumn: number) => [
  {
    column_index: 0,
    expected_text: "04/22",
    locator: {},
    proposed_meaning: "date",
  },
  {
    column_index: amountColumn,
    expected_text: "14.00",
    locator: {},
    proposed_meaning: "amount",
  },
]
const raw = () => ({
  id,
  case_id: id,
  evidence_file_id: id,
  status: "completed",
  request: {
    schema_version: "pdf-cell-nomination-v1",
    execution_mode: "simulated_test",
    page_number: 1,
    table_index: 0,
    source_revision: revision,
    case_id: id,
    evidence_file_id: id,
    provider: "test",
    model_id: "synthetic",
    prompt_sha256: revision,
  },
  request_sha256: revision,
  result: {
    rows: [
      { row_index: 0, reason: "synthetic", cells: cells(1) },
      { row_index: 1, reason: "shifted", cells: cells(2) },
    ],
    raw_response_sha256: revision,
    usage: {},
    source_revision: revision,
    prompt_version: "pdf-cell-nomination-v1",
  },
  error_code: null,
  created_at: "2026-09-10T00:00:00Z",
  completed_at: "2026-09-10T00:01:00Z",
  applied: false,
  limitation: "Unverified",
})
const source = () => ({
  case_id: id,
  evidence_file_id: id,
  page_number: 1,
  table_index: 0,
  table_count: 1,
  source_revision: revision,
  table_source: "text_alignment",
  geometry_source: "synthetic",
  locator: {},
  columns: [0, 1, 2],
  rows: raw().result.rows,
  applied: false,
})
describe("model nomination selection", () => {
  it("keeps shifted layouts separate and includes immutable attempt identity", () => {
    const plans = modelNominationPlans(
      pdfModelNomination.parse(raw()),
      [1, 0],
      source()
    )
    expect(plans).toHaveLength(2)
    expect(plans[0].nomination_id).toBe(id)
    expect(plans[0].columns).toEqual([
      { column_index: 0, meaning: "date" },
      { column_index: 1, meaning: "amount" },
      { column_index: 2, meaning: "unknown" },
    ])
    expect(plans[1].rows[0].cells[1].expected_text).toBe("14.00")
  })
  it("refuses changed sources, repeated selections and invented rows", () => {
    const run = pdfModelNomination.parse(raw())
    expect(() =>
      modelNominationPlans(run, [0], {
        ...source(),
        source_revision: "b".repeat(64),
      })
    ).toThrow("Source changed")
    expect(() => modelNominationPlans(run, [0, 0], source())).toThrow(
      "distinct"
    )
    expect(() => modelNominationPlans(run, [20], source())).toThrow(
      "original source"
    )
    run.result!.rows[0].cells[1].expected_text = "1400.00"
    expect(() => modelNominationPlans(run, [0], source())).toThrow(
      "original source"
    )
  })
  it("rejects inconsistent terminal and pending outcomes", () => {
    expect(
      pdfModelNomination.safeParse({ ...raw(), completed_at: null }).success
    ).toBe(false)
    expect(
      pdfModelNomination.safeParse({
        ...raw(),
        status: "pending",
        result: null,
      }).success
    ).toBe(false)
    expect(
      pdfModelNomination.safeParse({ ...raw(), status: "failed", result: null })
        .success
    ).toBe(false)
    expect(
      pdfModelNomination.safeParse({
        ...raw(),
        status: "pending",
        result: null,
        completed_at: null,
      }).success
    ).toBe(true)
  })
})
