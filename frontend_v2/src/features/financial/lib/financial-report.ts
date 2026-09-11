import { z } from "zod"
import { zipSync, strToU8 } from "fflate"
import { sha256Hex } from "@/lib/browser-crypto"
import { fetchAPI } from "@/lib/api-client"
import type {
  CaseworkEntry,
  CaseworkCreateInput,
} from "@/features/workspace/casework-api"
import { findingReport } from "./finding-report"
import { verifiedFindingSources } from "./finding-report-bundle"
import { readSavedTrace, traceFindingLinks } from "./saved-trace"
import { renderTraceReport } from "./trace-report"
import { readSavedIndirect, indirectWorkpaperSchema } from "./saved-indirect"
import { indirectCatalog } from "./indirect-review"
import { indirectWorkpaperReport } from "./indirect-workpaper-report"
import { transactionDetail } from "./transaction-detail"
import { correctionMoney } from "./correction-contract"

export const financialReportSchema = "loupe.financial.finding_report/1"
export const MAX_REPORT_NOTES = 20
const MAX_REPORT_BYTES = 8 * 1024 * 1024
const text = z.string()
const record = z.record(text, z.unknown())
const savedEntry = z.object({
  id: text.min(1),
  case_id: text.min(1),
  entry_type: z.enum(["note", "finding", "theory"]),
  title: text.nullish(),
  body: text,
  tags: z.array(text),
  version: z.number().int().positive(),
  review_state: z.enum(["accepted", "pending", "rejected"]),
  migration_metadata: record,
  needs_migration_review: z.boolean(),
  deleted_at: text.nullish(),
  author_name: text.nullish(),
  author_email: text.nullish(),
  created_at: text.nullish(),
  updated_at: text.nullish(),
  links: z
    .array(
      z.object({
        id: text,
        entry_id: text,
        case_id: text,
        target_id: text,
        target_type: z.enum([
          "evidence",
          "graph_entity",
          "dossier",
          "entry",
          "task",
          "deadline",
          "timeline_event",
          "agent_artifact",
          "witness",
        ]),
        target_label: text.nullish(),
        relationship: z.enum([
          "unclassified",
          "supports",
          "contradicts",
          "context",
        ]),
        source_anchor: record,
        metadata: record,
      })
    )
    .max(500),
})
const reportData = z.object({
  schema: z.literal(financialReportSchema),
  case_id: text.min(1),
  case_title: text,
  title: text.trim().min(1).max(255),
  introduction: text.max(8000),
  prepared_at: text.datetime(),
  notes: z.array(savedEntry).min(1).max(MAX_REPORT_NOTES),
})
const envelopeSchema = z.object({
  schema: z.literal(financialReportSchema),
  case_id: text,
  report_json: text.max(MAX_REPORT_BYTES),
  sha256: text.regex(/^[a-f0-9]{64}$/),
  bytes: z.number().int().positive().max(MAX_REPORT_BYTES),
})
export type FinancialReportEnvelope = z.infer<typeof envelopeSchema>
export type FinancialReport = {
  data: z.infer<typeof reportData>
  envelope: FinancialReportEnvelope
  html: string
  files: { id: string; label: string }[]
}
export type ReportSelection = { id: string; title: string; version: number }
export type FinancialReportDraft = {
  title: string
  introduction: string
  selected: ReportSelection[]
}
export const emptyReportDraft: FinancialReportDraft = {
  title: "",
  introduction: "",
  selected: [],
}
export const reportDraftName = "financial-report-builder"

export const reportEscape = (value: unknown) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!
  )
const bodyOf = (html: string) => {
  const result = html.match(/<body[^>]*>([\s\S]*)<\/body>/i)
  if (!result) throw Error("A report section could not be rendered.")
  return result[1]
}

function validateNotes(notes: CaseworkEntry[], caseId: string) {
  if (new Set(notes.map((note) => note.id)).size !== notes.length)
    throw Error("A note was selected more than once.")
  for (const note of notes) {
    if (
      note.case_id !== caseId ||
      note.deleted_at ||
      !note.tags.includes("financial")
    )
      throw Error("A selected note is unavailable or belongs to another case.")
    if (
      note.tags.includes("financial-report") ||
      note.links.some((link) => link.metadata.schema === financialReportSchema)
    )
      throw Error("Choose the original findings, not another compiled report.")
    if (
      note.links.some(
        (link) => link.case_id !== caseId || link.entry_id !== note.id
      )
    )
      throw Error("A note's supporting links do not match this case or note.")
    // Validate saved payment bindings before either preview or saving.
    findingReport(note, caseId)
  }
}

export function notePaymentTotals(note: CaseworkEntry) {
  const rows = new Map<string, z.infer<typeof transactionDetail>>()
  for (const link of note.links)
    for (const raw of Array.isArray(link.metadata.transactions)
      ? link.metadata.transactions
      : []) {
      const row = transactionDetail.parse(raw)
      const previous = rows.get(row.key)
      if (previous && JSON.stringify(previous) !== JSON.stringify(row))
        throw Error(
          "A note contains conflicting saved values for the same payment."
        )
      rows.set(row.key, row)
    }
  const groups = new Map<
    string,
    {
      account: string
      currency: string
      credits: bigint
      debits: bigint
      count: number
    }
  >()
  for (const row of rows.values()) {
    if (
      !["credit", "debit"].includes(row.direction) ||
      BigInt(row.amount_minor) < 0n
    )
      throw Error(
        "A saved payment has an unsupported amount or direction. Review it before reporting."
      )
    const key = JSON.stringify([row.account_id, row.currency])
    const group = groups.get(key) ?? {
      account: row.account_label || row.account_id,
      currency: row.currency,
      credits: 0n,
      debits: 0n,
      count: 0,
    }
    if (row.direction === "credit") group.credits += BigInt(row.amount_minor)
    else group.debits += BigInt(row.amount_minor)
    group.count++
    groups.set(key, group)
  }
  return { count: rows.size, groups: [...groups.values()] }
}

async function reportSections(
  data: FinancialReport["data"],
  paths?: Record<string, string>
) {
  const sections: string[] = [],
    sourceDigests: Record<string, string> = {}
  const bind = (id: string, digest: string | null | undefined) => {
    if (!digest) return
    if (sourceDigests[id] && sourceDigests[id] !== digest)
      throw Error(
        "Saved calculations disagree about the original version of a supporting file."
      )
    sourceDigests[id] = digest
  }
  for (let index = 0; index < data.notes.length; index++) {
    const note = data.notes[index] as CaseworkEntry
    const totals = notePaymentTotals(note)
    let extra = ""
    for (const link of note.links) {
      if (link.metadata.schema === "loupe.financial.saved_trace/1") {
        const trace = await readSavedTrace(link.metadata.envelope, data.case_id)
        const expected = await traceFindingLinks(trace)
        for (const source of expected) {
          const attached = note.links.filter(
            (item) =>
              item.target_type === "evidence" &&
              item.target_id === source.target_id &&
              item.metadata.trace_sha256 === trace.envelope.scenario_sha256
          )
          const ids = new Set(
            attached.flatMap((item) =>
              z
                .array(z.string())
                .parse(item.source_anchor.financial_transaction_ids)
            )
          )
          if (
            !z
              .array(z.string())
              .parse(source.source_anchor?.financial_transaction_ids)
              .every((id) => ids.has(id))
          )
            throw Error(
              "The tracing calculation is missing its saved payment references."
            )
        }
        extra += `<details open><summary>Saved tracing calculation</summary>${bodyOf(await renderTraceReport(trace))}</details>`
        const included = new Set(
          z.array(z.string()).parse(trace.value.inputs.ordered_transaction_ids)
        )
        const captured = JSON.parse(trace.envelope.scenario_json)
        for (const reading of captured.ledger_snapshot.ledger.readings) {
          if (included.has(reading.row.key) && reading.source.evidence_file_id)
            bind(
              reading.source.evidence_file_id,
              reading.source.sha256_at_ingestion
            )
        }
      }
      if (link.metadata.schema === indirectWorkpaperSchema) {
        if (link.metadata.catalog === undefined)
          throw Error(
            "The report is missing the method definition used by a saved calculation."
          )
        const saved = await readSavedIndirect(
          link,
          note.links,
          data.case_id,
          async () => {
            throw Error("The saved method definition is unavailable.")
          }
        )
        extra += `<details open><summary>Saved financial calculation</summary>${bodyOf(indirectWorkpaperReport(saved, note, paths))}</details>`
        for (const file of saved.review.value.sources)
          bind(file.id, file.sha256)
      }
    }
    const amounts = totals.groups
      .map(
        (group) =>
          `<tr><td>${reportEscape(group.account)}</td><td>${group.count}</td><td>${reportEscape(correctionMoney(String(group.credits), group.currency))}</td><td>${reportEscape(correctionMoney(String(group.debits), group.currency))}</td></tr>`
      )
      .join("")
    sections.push(
      `<section id="finding-${index + 1}" class="finding"><p class="chapter">Finding ${index + 1} · Saved note version ${note.version} · Review status: ${reportEscape(note.review_state)}</p>${bodyOf(findingReport(note, data.case_id, paths))}${amounts ? `<h2>Payment totals for this note</h2><p>Accounts and currencies are kept separate. A payment is counted once within this note. Credits and debits follow the account's statement.</p><table><thead><tr><th>Account</th><th>Payments</th><th>Credits</th><th>Debits</th></tr></thead><tbody>${amounts}</tbody></table>` : ""}${extra}</section>`
    )
  }
  return { sections, sourceDigests }
}

async function renderReport(
  data: FinancialReport["data"],
  paths?: Record<string, string>
) {
  const { sections, sourceDigests } = await reportSections(data, paths)
  const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${reportEscape(data.title)}</title><style>body{font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#202020;background:#fff}h1{font-size:28px}h2{font-size:21px}h3{font-size:17px}p,td,li,code{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.intro,.note{white-space:pre-wrap}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;border:1px solid #ccc;text-align:left;vertical-align:top}.muted,.chapter{color:#555;font-size:14px}.finding{border-top:2px solid #bbb;margin-top:40px;padding-top:24px}details{margin:24px 0}@media print{body{margin:0;padding:0;font-size:11pt}thead{display:table-header-group}tr{break-inside:avoid}.finding{break-before:page}a{color:inherit}}</style><body><h1>${reportEscape(data.title)}</h1><p>${reportEscape(data.case_title || "Financial investigation")}<br>Prepared ${reportEscape(data.prepared_at)}<br>Case ${reportEscape(data.case_id)}</p>${data.introduction ? `<h2>Introduction</h2><p class="intro">${reportEscape(data.introduction)}</p>` : ""}<h2>Included findings (${data.notes.length})</h2><ol>${data.notes.map((note, index) => `<li><a href="#finding-${index + 1}">${reportEscape(note.title || "Untitled note")}</a> · version ${note.version}</li>`).join("")}</ol><p>This report contains the selected saved notes, their payment values and their saved calculations. Values have not been updated for later transaction corrections. A payment discussed in several notes appears in each relevant note; totals are shown per note and must not be added together.</p><p>${paths ? "The selected supporting PDFs are included as whole files. They can contain other payments or periods." : "Original PDFs are not included in this document."}</p>${sections.join("")}<footer><p>End of selected findings. Prepared using ${financialReportSchema}.</p></footer></body></html>`
  return { html, sourceDigests }
}

export async function prepareFinancialReport(input: {
  caseId: string
  caseTitle: string
  title: string
  introduction: string
  notes: CaseworkEntry[]
}): Promise<FinancialReport> {
  const data = reportData.parse({
    schema: financialReportSchema,
    case_id: input.caseId,
    case_title: input.caseTitle,
    title: input.title,
    introduction: input.introduction,
    prepared_at: new Date().toISOString(),
    notes: input.notes,
  })
  validateNotes(data.notes, input.caseId)
  // Retain the method used to read a legacy workpaper so the report can be reopened offline.
  for (const note of data.notes)
    for (const link of note.links)
      if (
        link.metadata.schema === indirectWorkpaperSchema &&
        link.metadata.catalog === undefined
      ) {
        const saved = await readSavedIndirect(
          link,
          note.links,
          data.case_id,
          async () =>
            indirectCatalog.parse(
              await fetchAPI(
                `/api/financial/indirect-review-methods?case_id=${encodeURIComponent(data.case_id)}`
              )
            )
        )
        link.metadata.catalog = saved.catalog
      }
  const report_json = JSON.stringify(data)
  const bytes = strToU8(report_json)
  if (bytes.length > MAX_REPORT_BYTES)
    throw Error(
      "These findings exceed the 8 MB report limit. Select fewer findings or download a large calculation separately."
    )
  const envelope = {
    schema: financialReportSchema,
    case_id: input.caseId,
    report_json,
    bytes: bytes.length,
    sha256: await sha256Hex(bytes),
  }
  return readFinancialReport(envelope, input.caseId)
}

export async function readFinancialReport(
  raw: unknown,
  caseId: string
): Promise<FinancialReport> {
  const envelope = envelopeSchema.parse(raw)
  const bytes = strToU8(envelope.report_json)
  if (
    envelope.case_id !== caseId ||
    bytes.length !== envelope.bytes ||
    (await sha256Hex(bytes)) !== envelope.sha256
  )
    throw Error(
      "The saved report does not match its case or recorded contents."
    )
  const data = reportData.parse(JSON.parse(envelope.report_json))
  if (data.case_id !== caseId)
    throw Error("The report contains another case's findings.")
  validateNotes(data.notes, caseId)
  const { html } = await renderReport(data)
  const files = new Map<string, string>()
  for (const note of data.notes)
    for (const link of note.links)
      if (link.target_type === "evidence")
        files.set(link.target_id, link.target_label || "Supporting file")
  return {
    data,
    envelope,
    html,
    files: [...files].map(([id, label]) => ({ id, label })),
  }
}

export function reportSaveInput(report: FinancialReport): CaseworkCreateInput {
  return {
    entry_type: "note",
    title: report.data.title,
    body:
      report.data.introduction ||
      "Compiled financial findings. Open the saved report to read the selected notes and supporting records.",
    tags: ["financial", "financial-report"],
    links: report.data.notes.map((note, index) => ({
      target_type: "entry",
      target_id: note.id,
      target_label: note.title || "Untitled note",
      relationship: "context",
      source_anchor: { note_version: note.version },
      metadata:
        index === 0
          ? { schema: financialReportSchema, envelope: report.envelope }
          : {},
    })),
  }
}

export async function readSavedFinancialReport(
  entry: CaseworkEntry,
  caseId: string
) {
  if (entry.case_id !== caseId || entry.deleted_at)
    throw Error("The report is unavailable in this case.")
  const envelopes = entry.links.filter(
    (link) => link.metadata.schema === financialReportSchema
  )
  if (envelopes.length !== 1)
    throw Error("The saved report contents are missing or ambiguous.")
  const report = await readFinancialReport(
    envelopes[0].metadata.envelope,
    caseId
  )
  if (
    entry.links.length !== report.data.notes.length ||
    entry.links.some(
      (link) =>
        link.case_id !== caseId ||
        link.entry_id !== entry.id ||
        link.target_type !== "entry" ||
        !report.data.notes.some(
          (note) =>
            note.id === link.target_id &&
            note.version === link.source_anchor.note_version
        )
    ) ||
    new Set(entry.links.map((link) => link.target_id)).size !==
      entry.links.length
  )
    throw Error("The report's attached notes do not match its saved contents.")
  return report
}

export async function financialReportDownload(
  report: FinancialReport,
  includePdfs: boolean,
  signal: AbortSignal
) {
  const checked = await readFinancialReport(
    report.envelope,
    report.data.case_id
  )
  const { sourceDigests } = await reportSections(checked.data)
  const sources = includePdfs
    ? await verifiedFindingSources(
        checked.data.notes,
        checked.data.case_id,
        signal,
        sourceDigests
      )
    : null
  const { html } = sources
    ? await renderReport(checked.data, sources.paths)
    : checked
  const archive: Record<string, Uint8Array> = {
    ...(sources?.archive ?? {}),
    "report.html": strToU8(html),
    "saved-report.json": strToU8(JSON.stringify(checked.envelope, null, 2)),
  }
  const members = await Promise.all(
    Object.entries(archive).map(async ([path, bytes]) => ({
      path,
      bytes: bytes.length,
      sha256: await sha256Hex(bytes),
    }))
  )
  archive["contents.json"] = strToU8(
    JSON.stringify(
      {
        schema: "loupe.financial.finding_report_package/1",
        case_id: checked.data.case_id,
        report_sha256: checked.envelope.sha256,
        notes: checked.data.notes.map((note) => ({
          id: note.id,
          version: note.version,
          title: note.title,
        })),
        files:
          sources?.files.map((file) => ({
            id: file.id,
            filename: file.original_filename,
            path: sources.paths[file.id],
            sha256: file.sha256,
          })) ?? [],
        members,
      },
      null,
      2
    )
  )
  if (signal.aborted) throw Error("Report preparation was cancelled.")
  return zipSync(archive, { level: 0 })
}
