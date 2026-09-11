import { sha256Hex } from "@/lib/browser-crypto"
import { zipSync, strToU8 } from "fflate"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { findingReport } from "./finding-report"
const fileSchema = z.object({
  id: z.string().uuid(),
  case_id: z.string(),
  original_filename: z.string(),
  size: z.number().int().nonnegative(),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
})
const MAX_BYTES = 64 * 1024 * 1024
export async function findingReportBundle(
  entry: CaseworkEntry,
  caseId: string,
  signal: AbortSignal
) {
  if (
    entry.case_id !== caseId ||
    entry.links.some((link) => link.case_id !== caseId)
  )
    throw Error("The saved work does not match this case.")
  const ids = [
    ...new Set(
      entry.links
        .filter((link) => link.target_type === "evidence")
        .map((link) => link.target_id)
    ),
  ]
  if (!ids.length || ids.length > 20)
    throw Error("A report package needs between 1 and 20 supporting PDFs.")
  const files = []
  let total = 0
  for (const id of ids) {
    const file = fileSchema.parse(
      await fetchAPI(`/api/evidence/${encodeURIComponent(id)}`, { signal })
    )
    if (file.case_id !== caseId || file.id !== id)
      throw Error("A supporting file belongs to another case.")
    if (!file.original_filename.toLowerCase().endsWith(".pdf"))
      throw Error(
        "This package supports PDFs only. Download other supporting files separately from Evidence."
      )
    total += file.size
    if (total > MAX_BYTES)
      throw Error(
        "The supporting PDFs exceed 64 MB. Download the note and source files separately."
      )
    files.push(file)
  }
  const archive: Record<string, Uint8Array> = {}
  const paths: Record<string, string> = {}
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    const linkedIds = [
      ...new Set(
        entry.links
          .filter(
            (link) =>
              link.target_type === "evidence" && link.target_id === file.id
          )
          .flatMap((link) =>
            Array.isArray(link.source_anchor.financial_transaction_ids)
              ? link.source_anchor.financial_transaction_ids.filter(
                  (id): id is string => typeof id === "string"
                )
              : []
          )
      ),
    ]
    for (let offset = 0; offset < linkedIds.length; offset += 5)
      await Promise.all(
        linkedIds.slice(offset, offset + 5).map(async (id) => {
          const citation = z
            .object({
              case_id: z.string(),
              transaction_id: z.string(),
              evidence_file_id: z.string(),
              sha256_at_ingestion: z.string(),
              recorded_digest_matches: z.literal(true),
            })
            .parse(
              await fetchAPI(
                `/api/financial/ledger/${encodeURIComponent(id)}/source?${new URLSearchParams({ case_id: caseId })}`,
                { signal }
              )
            )
          if (
            citation.case_id !== caseId ||
            citation.transaction_id !== id ||
            citation.evidence_file_id !== file.id ||
            citation.sha256_at_ingestion !== file.sha256
          )
            throw Error(
              "A saved payment does not match its supporting PDF. No package was created."
            )
        })
      )
    const token = localStorage.getItem("authToken")
    const response = await fetch(
      `/api/evidence/${encodeURIComponent(file.id)}/file`,
      {
        signal,
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }
    )
    if (!response.ok || !response.body)
      throw Error(
        `Could not download ${file.original_filename}. No incomplete package was created.`
      )
    const reader = response.body.getReader(),
      chunks: Uint8Array[] = []
    let size = 0
    try {
      while (true) {
        const chunk = await reader.read()
        if (chunk.done) break
        size += chunk.value.byteLength
        if (size > file.size || size > MAX_BYTES)
          throw Error(
            "A supporting file changed size. Refresh the saved note before trying again."
          )
        chunks.push(chunk.value)
      }
    } finally {
      await reader.cancel().catch(() => {})
    }
    if (size !== file.size)
      throw Error("A supporting PDF was incomplete. No package was created.")
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) {
      bytes.set(chunk, offset)
      offset += chunk.length
    }
    const hash = await sha256Hex(bytes)
    if (hash !== file.sha256)
      throw Error(
        "A supporting PDF differs from its recorded original. No package was created."
      )
    const path = `statements/${i + 1}-${file.original_filename.replace(/[^a-zA-Z0-9._-]/g, "_").slice(-160)}`
    paths[file.id] = path
    archive[path] = bytes
  }
  archive["report.html"] = strToU8(findingReport(entry, caseId, paths))
  archive["references.json"] = strToU8(
    JSON.stringify(
      {
        case_id: caseId,
        entry_id: entry.id,
        entry_version: entry.version,
        files: files.map((file) => ({
          id: file.id,
          filename: file.original_filename,
          sha256: file.sha256,
          bytes: file.size,
          path: paths[file.id],
        })),
      },
      null,
      2
    )
  )
  return zipSync(archive, { level: 0 })
}
