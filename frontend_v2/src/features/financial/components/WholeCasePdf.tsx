import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { useWholeCaseRun, wholeCaseFileUrl } from "../lib/whole-case-run"
import { WholeCaseProgress } from "./WholeCaseProgress"

interface Summary {
  readings: number
  parts: number
  part_limit: number
  archive_bytes: number
  listed: { part: number; of: number; filename: string; readings: number; words: string }[]
}

/** A report above one PDF's size: written in the background as numbered parts that together cover every reading. */
export function WholeCasePdf({
  caseId,
  params,
  marking,
}: {
  caseId: string
  params: LedgerQueryParams
  marking: string
}) {
  const { run, error, again } = useWholeCaseRun<Summary>(caseId, {
    kind: "pdf",
    privilege_marking: marking,
    ...(params.accountId ? { account_id: params.accountId } : {}),
    ...(params.accountIds?.length ? { account_ids: params.accountIds } : {}),
    ...(params.accountHolders?.length ? { account_holders: params.accountHolders } : {}),
    ...(params.startDate ? { start_date: params.startDate } : {}),
    ...(params.endDate ? { end_date: params.endDate } : {}),
  })
  if (!run || run.status !== "completed" || !run.summary)
    return <WholeCaseProgress run={run} error={error} noun="PDF report" onAgain={again} />
  const summary = run.summary
  return (
    <div className="space-y-2 rounded border p-3 text-sm">
      <p>
        {summary.parts.toLocaleString("en-US")} numbered PDF parts cover all {summary.readings.toLocaleString("en-US")}{" "}
        captured readings, in date order, up to {summary.part_limit.toLocaleString("en-US")} in each.
      </p>
      <ul>
        {summary.listed.map((part) => (
          <li key={part.filename}>{part.words}</li>
        ))}
      </ul>
      <a className="underline" href={wholeCaseFileUrl(caseId, run.id, "ledger-report-parts.zip")} download>
        Download all parts ({(summary.archive_bytes / 1024 / 1024).toFixed(1)} MB)
      </a>
    </div>
  )
}
