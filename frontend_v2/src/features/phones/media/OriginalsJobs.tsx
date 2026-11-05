import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { cancelOriginals, getOriginals, originalsFileUrl, type OriginalsBundle } from "../api"
import { sizeWords } from "./media-tools"

const n = (v: number) => v.toLocaleString("en-US")
const failWords = (e: unknown) => (e instanceof Error && e.message ? e.message : "That could not be done.")

/** What a finished download holds, every file accounted for. */
function resultWords(b: OriginalsBundle): string {
  const parts = [`${n(b.matched)} match every stored hash`]
  if (b.no_stored_hash) parts.push(`${n(b.no_stored_hash)} have no stored hash`)
  if (b.mismatched) parts.push(`${n(b.mismatched)} differ from a stored hash and are included`)
  if (b.not_included) parts.push(`${n(b.not_included)} could not be included`)
  return `${n(b.files_total)} ${b.files_total === 1 ? "file" : "files"}: ${parts.join(", ")}. manifest.csv in the zip lists each one.`
}

function Job({ caseId, b, onChanged }: { caseId: string; b: OriginalsBundle; onChanged: () => void }) {
  const cancel = useMutation({ mutationFn: () => cancelOriginals(caseId, b.bundle_id), onSuccess: onChanged })
  const open = b.state === "queued" || b.state === "running"
  return (
    <li className="flex flex-wrap items-center gap-2" data-state={b.state}>
      <span className="font-medium">{b.scope_words}:</span>
      {b.state === "queued" && <span role="status">Waiting to start, {n(b.files_total)} files, {sizeWords(b.bytes_total)}.</span>}
      {b.state === "running" && (
        <>
          <progress max={b.bytes_total || b.files_total} value={b.bytes_total ? b.bytes_done : b.files_done} aria-label="Bytes written" />
          <span role="status">{n(b.files_done)} of {n(b.files_total)} files, {sizeWords(b.bytes_done)} of {sizeWords(b.bytes_total)}.</span>
        </>
      )}
      {open && <Button size="sm" variant="ghost" onClick={() => cancel.mutate()} disabled={cancel.isPending}>Cancel</Button>}
      {b.state === "done" && b.file && (
        <>
          <span>{resultWords(b)}</span>
          <a className="underline" href={originalsFileUrl(caseId, b.bundle_id)} download={b.file.filename}>Save the zip ({sizeWords(b.file.size)})</a>
          <span className="break-all font-mono text-muted-foreground" title="SHA-256 of the zip">{b.file.sha256}</span>
        </>
      )}
      {b.state === "failed" && <span role="alert">{b.error}</span>}
      {b.state === "cancelled" && <span>Cancelled; nothing was kept.</span>}
      {b.state === "removed" && <span>The zip was removed after its days were up. Choose the files and ask again.</span>}
      {cancel.isError && <span role="alert">{failWords(cancel.error)}</span>}
    </li>
  )
}

/** The case's recent Download originals jobs (03 8.3), with true progress in files and bytes while one runs. */
export function OriginalsJobs({ caseId }: { caseId: string }) {
  const client = useQueryClient()
  const q = useQuery({
    queryKey: ["phone-originals", caseId],
    queryFn: () => getOriginals(caseId),
    enabled: !!caseId,
    refetchInterval: (query) => (query.state.data?.items.some((b) => b.state === "queued" || b.state === "running") ? 2000 : false),
  })
  const items = q.data?.items ?? []
  if (!items.length) return null
  return (
    <section aria-label="Originals downloads" className="rounded border p-2 text-xs">
      <ul className="flex flex-col gap-1">
        {items.map((b) => <Job key={b.bundle_id} caseId={caseId} b={b} onChanged={() => void client.invalidateQueries({ queryKey: ["phone-originals", caseId] })} />)}
      </ul>
    </section>
  )
}
