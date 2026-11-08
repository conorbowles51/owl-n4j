import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, LoaderCircle, Package, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ACTIVE_EXPORT_STATUSES,
  caseExportsAPI,
  type CaseExport,
} from "../exports-api"

const STATUS_WORDS: Record<CaseExport["status"], string> = {
  queued: "Waiting to start",
  running: "Being built",
  cancelling: "Stopping",
  complete: "Ready to download",
  failed: "Failed",
  cancelled: "Cancelled",
  expired: "Removed after its keep time",
  removed: "Removed",
}

const size = (bytes: number | null) => {
  if (bytes == null) return ""
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
const when = (value: string | null) => (value ? new Date(value).toLocaleString() : "")

function ExportRow({ row, caseId, onChanged }: { row: CaseExport; caseId: string; onChanged: () => void }) {
  const [actionError, setActionError] = useState<string | null>(null)
  const active = (ACTIVE_EXPORT_STATUSES as readonly string[]).includes(row.status)
  const act = useMutation({
    mutationFn: (what: "cancel" | "remove") =>
      what === "cancel" ? caseExportsAPI.cancel(caseId, row.id) : caseExportsAPI.remove(caseId, row.id),
    onSuccess: onChanged,
    onError: (error) => setActionError((error as Error).message),
  })
  return (
    <div className="rounded-md border border-border p-3 text-sm" data-testid="case-export-row">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {active && <LoaderCircle className="size-3.5 animate-spin text-muted-foreground" />}
          <span className="font-medium">{STATUS_WORDS[row.status]}</span>
          <span className="text-xs text-muted-foreground">
            asked for by {row.requested_by}, {when(row.created_at)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {row.status === "complete" && (
            <Button asChild size="sm" variant="outline">
              {/* A package can run to many gigabytes: a plain link lets the browser stream it to disk. */}
              <a href={caseExportsAPI.downloadUrl(caseId, row.id)} download>
                <Download className="size-3.5" />
                Download ({size(row.size_bytes)})
              </a>
            </Button>
          )}
          {active && (
            <Button size="sm" variant="ghost" disabled={act.isPending} onClick={() => act.mutate("cancel")}>
              <X className="size-3.5" />
              Cancel
            </Button>
          )}
          {!active && row.status !== "removed" && row.status !== "expired" && (
            <Button size="sm" variant="ghost" disabled={act.isPending} onClick={() => act.mutate("remove")}>
              Remove
            </Button>
          )}
        </div>
      </div>
      {active && (
        <p className="mt-1.5 text-xs text-muted-foreground" data-testid="case-export-progress">
          {row.phase ?? "Starting"}
          {row.total > 0 ? ` (${row.done} of ${row.total} steps)` : ""}
        </p>
      )}
      {row.status === "failed" && row.error && (
        <p role="alert" className="mt-1.5 text-xs text-destructive">
          {row.error}
        </p>
      )}
      {row.status === "complete" && (
        <div className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
          <p data-testid="case-export-contents">
            {row.tables?.toLocaleString()} tables, {row.rows?.toLocaleString()} records,{" "}
            {row.evidence_files?.toLocaleString()} evidence files
            {row.graph ? `, graph ${row.graph.nodes.toLocaleString()} nodes` : ""}
            {row.expires_at ? `. Kept until ${when(row.expires_at)}.` : ""}
          </p>
          {(row.missing_from_disk ?? 0) > 0 && (
            <p role="alert" className="text-destructive">
              {row.missing_from_disk} evidence files were missing from disk and are not in the package.
            </p>
          )}
          {row.rows_private_to_others_left_out &&
            Object.keys(row.rows_private_to_others_left_out).length > 0 && (
              <p>
                Left out as private to other people:{" "}
                {Object.entries(row.rows_private_to_others_left_out)
                  .map(([table, n]) => `${n} ${table.replace(/_/g, " ")}`)
                  .join(", ")}
                .
              </p>
            )}
          <p className="break-all">SHA-256 {row.sha256}</p>
        </div>
      )}
      {actionError && (
        <p role="alert" className="mt-1.5 text-xs text-destructive">
          {actionError}
        </p>
      )}
    </div>
  )
}

/**
 * Whole-case export: the complete case as one portable package, for a copy that leaves this installation.
 * The server allows the case owner and super admins only; everything shown here states what the package holds.
 */
export function CaseExportsSection({ caseId }: { caseId: string }) {
  const queryClient = useQueryClient()
  const list = useQuery({
    queryKey: ["case-exports", caseId],
    queryFn: () => caseExportsAPI.list(caseId),
    refetchInterval: (query) =>
      query.state.data?.exports.some((row) =>
        (ACTIVE_EXPORT_STATUSES as readonly string[]).includes(row.status)
      )
        ? 5000
        : false,
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["case-exports", caseId] })
  const request = useMutation({ mutationFn: () => caseExportsAPI.request(caseId), onSettled: refresh })
  const data = list.data
  const hasActive = data?.exports.some((row) => (ACTIVE_EXPORT_STATUSES as readonly string[]).includes(row.status))

  return (
    <Card className="mt-6 gap-4 p-5" aria-labelledby="case-exports-title">
      <CardHeader className="grid-cols-[auto_1fr] grid-rows-[auto_auto] gap-x-3">
        <div className="row-span-2 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
          <Package className="size-4" />
        </div>
        <CardTitle id="case-exports-title" className="self-end text-base">
          Export the whole case
        </CardTitle>
        <CardDescription>
          One portable package, for moving or copying this case to another Loupe installation.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {data && (
          <div className="space-y-1 text-sm text-muted-foreground">
            <p data-testid="case-export-holds" className="text-foreground">
              {data.holds}
            </p>
            <p>{data.private_note}</p>
            <p>
              {data.left_out} {data.kept}
            </p>
          </div>
        )}
        <div className="flex items-center gap-3">
          <Button
            disabled={!data || hasActive || request.isPending}
            onClick={() => request.mutate()}
          >
            {request.isPending || hasActive ? <LoaderCircle className="animate-spin" /> : <Package />}
            {hasActive ? "An export is running" : "Build the package"}
          </Button>
          {request.isError && (
            <p role="alert" className="text-sm text-destructive">
              {(request.error as Error).message}
            </p>
          )}
        </div>
        {list.isError && (
          <p role="alert" className="text-sm text-destructive">
            {(list.error as Error).message || "The exports could not be read."}
          </p>
        )}
        {data && data.exports.length > 0 && (
          <div className="space-y-2">
            {data.exports.map((row) => (
              <ExportRow key={row.id} row={row} caseId={caseId} onChanged={refresh} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
