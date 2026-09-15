import type { PaymentDocumentProposal } from "./payment-document"
export const wireFixture: PaymentDocumentProposal = {
  schema: "loupe.financial.payment_document/1",
  version: "test",
  kind: "wire_report",
  case_id: "case",
  evidence_file_id: "wire-file",
  filename: "synthetic-wire.pdf",
  revision: "a".repeat(64),
  file_sha256: "b".repeat(64),
  supported: true,
  page_numbers: [1],
  creates_transactions: false,
  issues: [],
  fields: [
    {
      key: "wire_amount",
      label: "Wire amount",
      input_type: "amount",
      raw: "120.00",
      value: "120.00",
    },
    {
      key: "currency",
      label: "Wire currency",
      input_type: "currency",
      raw: "USD/120.00",
      value: "USD",
    },
    {
      key: "value_date",
      label: "Value date",
      input_type: "date",
      raw: "03/23/2021",
      value: "2021-03-23",
    },
    {
      key: "sending_party",
      label: "Sending party",
      input_type: "text",
      raw: "EXAMPLE SENDER",
      value: "EXAMPLE SENDER",
    },
  ].map((f) => ({
    ...f,
    input_type: f.input_type as "amount" | "currency" | "date" | "text",
    printed_label: f.label + ":",
    issues: [],
    source_cells: [
      { expected_text: f.raw, locator: { kind: "page_only", page: 1 } },
    ],
  })),
}
export const wireCapture = () => ({
  schema: wireFixture.schema,
  original: structuredClone(wireFixture),
  reviewed_values: Object.fromEntries(
    wireFixture.fields.map((f) => [f.key, f.value])
  ),
  correction_reasons: {} as Record<string, string>,
  notes: "Check the purpose.",
  link_reason: "",
})
