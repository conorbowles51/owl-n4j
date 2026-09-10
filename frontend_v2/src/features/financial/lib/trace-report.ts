import type { TraceAssetResults } from "./trace-assets"
import { z } from "zod"
import { traceScenarioSchema, type verifyTraceResponse } from "./ledger-trace"
import {
  networkTraceScenarioSchema,
  type verifyNetworkTrace,
} from "./network-trace"
import { correctionMoney } from "./correction-contract"
export type VerifiedTrace =
  | Awaited<ReturnType<typeof verifyTraceResponse>>
  | Awaited<ReturnType<typeof verifyNetworkTrace>>
const esc = (value: unknown) =>
  String(value ?? "Unknown").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!
  )
const table = (headers: string[], rows: unknown[][]) =>
  `<table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`

function assetReport(assets: TraceAssetResults) {
  if (!assets.length)
    return "<h3>Separate asset interpretations</h3><p>None selected.</p>"
  return (
    "<h3>Separate asset interpretations</h3><p>These interpretations do not change the cash tracing results.</p>" +
    assets
      .map((asset) => {
        const allocations = (
          values: Record<string, string>,
          outside: string,
          unidentified: string,
          unfunded: string
        ) =>
          table(
            ["Allocation", "Amount"],
            [
              ...Object.entries(values).map(([claim, amount]) => [
                `Claim: ${claim}`,
                correctionMoney(amount, asset.currency),
              ]),
              ["Outside claims", correctionMoney(outside, asset.currency)],
              ["Unidentified", correctionMoney(unidentified, asset.currency)],
              ["Unfunded", correctionMoney(unfunded, asset.currency)],
            ]
          )
        return (
          `<h4>${esc(asset.asset_label)}</h4><p>Withdrawal source: ${esc(asset.transaction_id)}</p><p>Basis: ${esc(asset.basis)}</p>` +
          table(
            [
              "Withdrawal",
              "Asset portion",
              "Remaining withdrawal",
              "Allocation basis",
            ],
            [
              [
                correctionMoney(asset.amount_minor, asset.currency),
                correctionMoney(
                  asset.asset_amount_minor ?? asset.amount_minor,
                  asset.currency
                ),
                asset.remaining_withdrawal_minor === undefined
                  ? "Not separately recorded"
                  : correctionMoney(
                      asset.remaining_withdrawal_minor,
                      asset.currency
                    ),
                asset.allocation_basis?.replaceAll("_", " ") ??
                  "Not separately recorded",
              ],
            ]
          ) +
          allocations(
            asset.allocated_by_claim,
            asset.outside_claims_minor,
            asset.unidentified_minor,
            asset.unfunded_minor
          ) +
          `<p>${esc(asset.limitation)}</p>` +
          (asset.resale
            ? `<h4>Resale interpretation</h4><p>Receipt source: ${esc(asset.resale.transaction_id)}. Proceeds: ${esc(correctionMoney(asset.resale.proceeds_minor, asset.currency))}.</p><p>Basis: ${esc(asset.resale.basis)}</p>` +
              allocations(
                asset.resale.allocated_by_claim,
                asset.resale.outside_claims_minor,
                asset.resale.unidentified_minor,
                asset.resale.unfunded_minor
              ) +
              `<p>${esc(asset.resale.limitation)}</p>`
            : "")
        )
      })
      .join("")
  )
}

export type TraceReportMarking =
  | "unmarked"
  | "confidential"
  | "privileged_confidential"
export async function renderTraceReport(
  trace: VerifiedTrace,
  marking: TraceReportMarking = "unmarked"
) {
  const markingLabel = {
    unmarked: "No privilege marking selected",
    confidential: "Confidential",
    privileged_confidential: "Privileged and confidential",
  }[marking]
  if (!markingLabel) throw Error("Unsupported report marking.")
  const { envelope } = trace
  const bytes = new TextEncoder().encode(envelope.scenario_json)
  const digest = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  if (
    digest !== envelope.scenario_sha256 ||
    bytes.length !== envelope.scenario_byte_count
  )
    throw Error("Scenario changed before report creation.")
  const captured = JSON.parse(envelope.scenario_json)
  if (
    captured.case_id !== trace.value.case_id ||
    captured.schema !== trace.value.schema
  )
    throw Error("Report scope does not match the verified scenario.")
  const value =
    captured.schema === "loupe.financial.conditional_trace/1"
      ? traceScenarioSchema.parse(captured)
      : networkTraceScenarioSchema.parse(captured)
  const sourceLedger = z
    .object({
      case_id: z.string(),
      readings: z
        .array(
          z.object({
            row: z.object({
              key: z.string(),
              ref_id: z.string().nullable().optional(),
              ordering_date: z.string(),
              description: z.string().nullable(),
              amount_minor: z.string().regex(/^-?[0-9]+$/),
              currency: z.string(),
              proof_class: z.string(),
              locator: z
                .object({ page: z.number().int().positive().optional() })
                .passthrough()
                .nullable()
                .optional(),
            }),
            source: z.object({
              id: z.string(),
              evidence_file_id: z.string().nullable(),
              sha256_at_ingestion: z.string(),
            }),
          })
        )
        .max(25000),
    })
    .parse(captured.ledger_snapshot?.ledger)
  if (sourceLedger.case_id !== value.case_id)
    throw Error("Captured source ledger belongs to another case.")
  const parts = [
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>Loupe conditional tracing report</title><style>body{font:15px/1.5 system-ui,sans-serif;color:#18202c;max-width:1100px;margin:30px auto;padding:20px}h1{color:#a51b34}table{table-layout:fixed;border-collapse:collapse;width:100%;margin:18px 0}td,th{border:1px solid #aab2bc;padding:8px;text-align:left;overflow-wrap:anywhere;vertical-align:top}th{background:#eef1f5}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}code{overflow-wrap:anywhere}@page{@bottom-left{content:"${markingLabel}"}}@media print{body{font-size:10pt;margin:0}h2,h3{break-after:avoid}tr{break-inside:avoid}thead{display:table-header-group}}</style></head><body><h1>Conditional tracing report</h1><p>${esc(markingLabel)}. Marking selected for this report; not a legal privilege determination.</p><p>Case: ${esc(value.case_id)}</p><p>Investigator-supplied assumptions are unverified. These calculations do not change the ledger or establish which legal tracing rule applies.</p><h2>Scope and limitations</h2><ul>${value.limitations.map((note) => `<li>${esc(note)}</li>`).join("")}</ul>`,
  ]
  if ("comparison" in value) {
    for (const [method, result] of Object.entries(value.comparison.results)) {
      parts.push(
        `<h2>${esc(method.replaceAll("_", " "))}</h2>`,
        table(
          ["Claim", "Attributed", "Remaining in account", "Withdrawn"],
          Object.entries(result.outcomes).map(([claim, o]) => [
            claim,
            correctionMoney(o.deposited.minor_units, o.deposited.currency),
            correctionMoney(o.surviving.minor_units, o.surviving.currency),
            correctionMoney(o.withdrawn.minor_units, o.withdrawn.currency),
          ])
        ),
        `<ul>${result.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`,
        assetReport(value.asset_uses[method] ?? [])
      )
    }
  } else {
    const currency = String(value.inputs.currency)
    for (const [method, result] of Object.entries(value.results)) {
      parts.push(
        `<h2>${esc(method.replaceAll("_", " "))}</h2>`,
        table(
          [
            "Claim",
            "Root attribution",
            "Remaining across accounts",
            "Withdrawn without selected transfer",
          ],
          Object.entries(result.claims).map(([claim, o]) => [
            claim,
            correctionMoney(o.root_attributed_minor, currency),
            correctionMoney(o.reported_remaining_minor, currency),
            correctionMoney(
              o.withdrawn_without_selected_transfer_minor,
              currency
            ),
          ])
        ),
        table(
          [
            "From account",
            "To account",
            "Debit source row",
            "Credit source row",
            "Amount",
            "Backward timing assumed",
          ],
          result.hops.map((h) => [
            h.from_account,
            h.to_account,
            h.debit_id,
            h.credit_id,
            correctionMoney(h.amount_minor, currency),
            h.backward_timing ? "Yes" : "No",
          ])
        ),
        assetReport(result.asset_uses)
      )
    }
  }
  parts.push(
    "<h2>Captured source readings</h2><p>These are captured ledger readings, including any excluded context. Their presence does not mean they contributed to the calculation.</p>",
    table(
      [
        "Reference",
        "Ordering date",
        "Description",
        "Amount",
        "Proof class",
        "Source file / page",
      ],
      sourceLedger.readings.map((r) => [
        r.row.ref_id || r.row.key,
        r.row.ordering_date,
        r.row.description,
        correctionMoney(r.row.amount_minor, r.row.currency),
        r.row.proof_class,
        `${r.source.evidence_file_id || r.source.id} / ${r.row.locator?.page ?? "unavailable"}`,
      ])
    )
  )
  parts.push(
    `<h2>Captured assumptions</h2><pre>${esc(JSON.stringify(value.inputs, null, 2))}</pre><h2>Source and calculation audit</h2><p>The full captured scenario below retains source readings, locations, original proof classes, account allocations, asset-use assumptions/results and method details. It may include readings excluded from the calculation. Refer to the scope and limitations above.</p><pre>${esc(envelope.scenario_json)}</pre><h2>Integrity reference</h2><p>Original scenario SHA-256: <code>${esc(digest)}</code>. Original scenario size: ${bytes.length} UTF-8 bytes. This digest identifies the original JSON, not the HTML report. Retain the separately downloadable JSON with this report.</p></body></html>`
  )
  const html = parts.join("")
  if (new TextEncoder().encode(html).length > 32 * 1024 * 1024)
    throw Error(
      "Readable scenario report exceeds 32 MiB; keep the original JSON or narrow the scenario."
    )
  return html
}
