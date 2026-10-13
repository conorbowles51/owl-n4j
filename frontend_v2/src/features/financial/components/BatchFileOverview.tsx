import { z } from "zod"
import { copyLine } from "../lib/statement-copies"

export const batchFileOverview = z.array(
  z.object({
    file_id: z.string(),
    filename: z.string(),
    statements: z.number().int().nonnegative(),
    copies: z.number().int().nonnegative(),
    unfinished: z.number().int().nonnegative(),
    saved: z.number().int().nonnegative(),
    all_copies: z.boolean(),
    retained: z.array(
      z.object({
        filename: z.string(),
        evidence_file_id: z.string().nullish(),
        copies: z.number().int().nonnegative(),
      })
    ),
  })
)
export type BatchFileOverviewEntry = z.infer<typeof batchFileOverview>[number]

const names = (entry: BatchFileOverviewEntry) =>
  entry.retained.map((retained) => retained.filename)

/**
 * Which files in the batch are only copies of statements kept elsewhere, and
 * which are partly copies — stated before any file or statement is opened.
 */
export function BatchFileOverview({
  files,
}: {
  files: BatchFileOverviewEntry[]
}) {
  const onlyCopies = files.filter((file) => file.all_copies)
  const partly = files.filter((file) => !file.all_copies && file.copies > 0)
  if (!onlyCopies.length && !partly.length) return null
  const copyStatements = onlyCopies.reduce(
    (sum, file) => sum + file.statements,
    0
  )
  return (
    <section
      aria-label="Copies in this batch"
      className="space-y-2 rounded border bg-card p-4"
    >
      <h3 className="font-semibold">Copies found before review</h3>
      <p className="text-sm text-muted-foreground">
        These statements match a statement kept in another file. They are set
        aside, not deleted, and are left out of the statements to review. Open
        one only if you want to check or restore it.
      </p>
      {partly.length > 0 && (
        <ul
          className="space-y-1 text-sm"
          aria-label="Files that are partly copies"
        >
          {partly.map((file) => (
            <li key={file.file_id} className="break-words">
              <strong>{file.filename}</strong>:{" "}
              {copyLine(file.copies, file.statements, names(file))}.{" "}
              {file.unfinished} still to review.
            </li>
          ))}
        </ul>
      )}
      {onlyCopies.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">
            {onlyCopies.length === 1
              ? `1 file is only copies (${copyStatements} statements) — nothing to review`
              : `${onlyCopies.length} files are only copies (${copyStatements} statements) — nothing to review`}
          </summary>
          <ul
            className="mt-2 space-y-1"
            aria-label="Files that are only copies"
          >
            {onlyCopies.map((file) => (
              <li key={file.file_id} className="break-words">
                <strong>{file.filename}</strong>:{" "}
                {copyLine(file.copies, file.statements, names(file))}.
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
