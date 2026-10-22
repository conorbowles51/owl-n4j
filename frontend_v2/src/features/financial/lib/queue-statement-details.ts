import { z } from "zod"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { newReviewId } from "./statement-review-id"
import type { QueueEntry } from "./review-queue"

/**
 * The queue's own use of the account-details path that the shared fix ("Fix
 * all N together") saves through: list a statement's current revision,
 * preview the change, then save that exact preview. Nothing here decides
 * whether a statement can be imported; every save is checked again on the
 * server exactly as the shared fix is.
 */
const ENDPOINT = "/api/financial/statement-import/account-details"

const statement = z.object({
  key: z.string(),
  file_id: z.string(),
  source_id: z.string().nullable(),
  statement_id: z.string().nullable(),
  revision: z.string(),
  filename: z.string(),
  status: z.string(),
  values: z.record(z.string(), z.string()),
})
export type DetailsStatement = z.infer<typeof statement>
const listing = z.object({
  case_id: z.string(),
  items: z.array(statement),
  notices: z.array(z.object({ filename: z.string(), message: z.string() })),
})
const changes = z.record(
  z.string(),
  z.object({ before: z.string(), after: z.string(), confirmed: z.boolean().optional() })
)
const preview = z.object({
  case_id: z.string(),
  preview_revision: z.string(),
  updated: z.number(),
  items: z.array(
    statement.extend({
      changes,
      excluded_reason: z.string().nullable().optional(),
      refreshed: z
        .record(z.string(), z.object({ listed: z.string(), current: z.string() }))
        .nullish(),
      conflicts: z.array(z.string()).nullish(),
    })
  ),
})
export type DetailsPreview = z.infer<typeof preview>
const receipt = z.object({
  case_id: z.string(),
  updated: z.number(),
  unchanged: z.number(),
  imported: z.number(),
  drafts: z.number(),
})

export type DetailChanges = {
  holder?: string
  institution?: string
  currency?: string
  account_number?: string
  no_activity_confirmed?: true
}

const scopeOf = (statementId?: string | null) => statementId || ""

/** The files a queue entry's statement may be listed under (its own and its copies'). */
export const entryFiles = (entry: QueueEntry) => [...new Set([entry.file_id, ...entry.file_ids])]

/** The listed statement that is this queue entry, or null when its file lists it no more. */
export function matchEntry(entry: QueueEntry, rows: DetailsStatement[]) {
  const files = new Set(entryFiles(entry))
  return (
    rows.find(
      (row) => files.has(row.file_id) && scopeOf(row.statement_id) === scopeOf(entry.statement_id)
    ) ?? null
  )
}

/** Lists the files' statements with their current revisions (read only). */
export async function listStatements(caseId: string, fileIds: string[]) {
  const result = listing.parse(
    await fetchAPI(`${ENDPOINT}/statements?case_id=${caseId}`, {
      method: "POST",
      body: { file_ids: fileIds },
    })
  )
  if (result.case_id !== caseId) throw Error("These statements belong to another case.")
  return result
}

const statusOf = (error: unknown) => (error instanceof ApiError ? error.status : 0)

type Mode = "fill_missing" | "replace"
const requestBody = (
  targets: DetailsStatement[],
  change: DetailChanges,
  mode: Mode,
  requestId: string,
  readCurrent: boolean
) => ({
  targets: targets.map(({ file_id, source_id, statement_id, revision }) => ({
    file_id,
    source_id,
    statement_id,
    revision,
  })),
  changes: change,
  mode,
  request_id: requestId,
  ...(readCurrent ? { read_current: true } : {}),
})

/** One planned change, and how to save exactly it. */
export type PlannedDetails = {
  preview: DetailsPreview
  conflicts: DetailsPreview["items"]
  save: () => Promise<z.infer<typeof receipt>>
}

/**
 * Previews one change for the listed statements, as the shared fix does. A
 * statement read again since it was listed is previewed as it reads now
 * (once). `save` then saves exactly this preview, with the same request id.
 */
export async function previewDetails(
  caseId: string,
  targets: DetailsStatement[],
  change: DetailChanges,
  mode: Mode = "replace"
): Promise<PlannedDetails> {
  const requestId = newReviewId()
  let readCurrent = false
  const ask = () =>
    fetchAPI(`${ENDPOINT}/preview?case_id=${caseId}`, {
      method: "POST",
      body: requestBody(targets, change, mode, requestId, readCurrent),
    })
  let planned: DetailsPreview
  try {
    planned = preview.parse(await ask())
  } catch (error) {
    if (statusOf(error) !== 409) throw error
    readCurrent = true
    planned = preview.parse(await ask())
  }
  if (planned.case_id !== caseId) throw Error("The preview belongs to another case.")
  return {
    preview: planned,
    conflicts: planned.items.filter((item) => item.conflicts?.length),
    save: async () => {
      const saved = receipt.parse(
        await fetchAPI(`${ENDPOINT}/save?case_id=${caseId}`, {
          method: "POST",
          body: {
            ...requestBody(targets, change, mode, requestId, readCurrent),
            preview_revision: planned.preview_revision,
          },
          timeout: 300000,
        })
      )
      if (saved.case_id !== caseId) throw Error("The save response belongs to another case.")
      return saved
    },
  }
}

/**
 * Previews then saves one change. A preview that changes nothing, or that
 * finds a field the reading now fills differently, is returned unsaved.
 */
export async function previewAndSave(
  caseId: string,
  targets: DetailsStatement[],
  change: DetailChanges,
  mode: Mode = "replace"
) {
  const planned = await previewDetails(caseId, targets, change, mode)
  if (!planned.preview.updated || planned.conflicts.length)
    return { saved: null, preview: planned.preview, conflicts: planned.conflicts }
  return { saved: await planned.save(), preview: planned.preview, conflicts: planned.conflicts }
}

const LABELS: Record<string, string> = {
  holder: "account holder",
  institution: "bank",
  currency: "currency",
  account_number: "account number",
  no_activity_confirmed: "no payments confirmed",
}

/** "currency EUR, bank Banorte" — what a preview changes for one statement. */
export function changeLine(item: DetailsPreview["items"][number]) {
  return Object.entries(item.changes)
    .map(([field, value]) =>
      value.confirmed || field === "no_activity_confirmed"
        ? LABELS[field] ?? field
        : `${LABELS[field] ?? field} ${value.after || "cleared"}`
    )
    .join(", ")
}
