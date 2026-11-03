import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { JobTray } from "@/components/ui/job-tray"
import { cancelImageIndex, createImageIndex, describeImageIndex, getImageIndexJobs, searchImages, type ImageSearchResults } from "../api"
import { coverageWords, imageLeftOutWords, indexJob } from "./image-search-words"
import { useObjectUrl } from "./use-object-url"

const n = (v: number) => v.toLocaleString("en-US")
const PAGE = 24

function ResultThumb({ caseId, fileUid, name, blur }: { caseId: string; fileUid: string; name: string; blur: boolean }) {
  const shown = useObjectUrl(caseId, fileUid, true, "thumbnail")
  return (
    <div className="flex h-28 w-28 shrink-0 items-center justify-center overflow-hidden rounded bg-muted text-center text-[11px]">
      {shown && "url" in shown ? <img src={shown.url} alt={name} className={`h-full w-full object-cover ${blur ? "blur-md" : ""}`} />
        : shown && "error" in shown ? <span className="px-2">{shown.error}</span>
        : <span className="px-2 text-muted-foreground">Image</span>}
    </div>
  )
}

/**
 * Image search by description (05 17.6): index the case's images on this server with true counts first, then find
 * them by words. Results are ranked by a model; each points to an image and opens to its file and messages. The
 * score is shown only as a rank.
 */
export function ImageSearch({ caseId, blur, onOpen }: { caseId: string; blur: boolean; onOpen: (fileUid: string) => void }) {
  const client = useQueryClient()
  const [now, setNow] = useState(() => Date.now())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [asked, setAsked] = useState<{ query: string; limit: number } | null>(null)
  const facts = useQuery({ queryKey: ["image-index-facts", caseId], queryFn: () => describeImageIndex(caseId), enabled: !!caseId })
  const jobs = useQuery({
    queryKey: ["image-index-jobs", caseId],
    queryFn: () => getImageIndexJobs(caseId),
    enabled: !!caseId,
    refetchInterval: (q) => (q.state.data?.items.some((j) => j.state === "running") ? 1000 : false),
  })
  const running = jobs.data?.items.some((j) => j.state === "running") ?? false
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [running])
  const results = useQuery({
    queryKey: ["image-search", caseId, asked?.query, asked?.limit],
    queryFn: () => searchImages(caseId, asked?.query ?? "", asked?.limit ?? PAGE),
    enabled: !!caseId && !!asked,
    placeholderData: (prev) => prev,
  })
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["image-index-jobs", caseId] })
    await client.invalidateQueries({ queryKey: ["image-index-facts", caseId] })
  }
  const start = async () => {
    setBusy(true)
    setError(null)
    try {
      await createImageIndex(caseId)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Indexing could not be started.")
    } finally {
      setBusy(false)
    }
  }
  const cancel = (id: string) => async () => {
    try {
      await cancelImageIndex(caseId, id)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Indexing could not be stopped.")
    }
  }
  const f = facts.data
  const tray = (jobs.data?.items ?? []).map((j) => indexJob(j, j.state === "running" ? cancel(j.id) : undefined))
  const r: ImageSearchResults | undefined = results.data
  const q = draft.trim()
  return (
    <section aria-label="Image search" className="flex flex-col gap-2 rounded border p-2 text-xs">
      <div className="flex flex-wrap items-start gap-2">
        {f && !f.model_installed && <p role="note">{f.model_words}</p>}
        {f && f.model_installed && f.eligible > 0 && (
          <span className="flex flex-col gap-0.5">
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void start()}>
              Index this case's images for search ({n(f.eligible)} {f.eligible === 1 ? "image" : "images"})
            </Button>
            {imageLeftOutWords(f) && <span className="text-muted-foreground">{imageLeftOutWords(f)}</span>}
            <span className="text-muted-foreground">{f.population_words} Indexed on this server; nothing is sent anywhere.</span>
          </span>
        )}
        {tray.length > 0 && <JobTray jobs={tray} now={now} />}
      </div>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (q) setAsked({ query: q, limit: PAGE }) }}>
        <label className="flex flex-col gap-0.5">Find images by description
          <input className="w-80 rounded border bg-background px-1 py-0.5" value={draft} maxLength={300} onChange={(e) => setDraft(e.target.value)} placeholder="for example: a handwritten note" />
        </label>
        <Button size="sm" type="submit" disabled={!q || results.isFetching}>Find</Button>
        {f && <span className="self-center text-muted-foreground">{coverageWords(f)}</span>}
      </form>
      {error && <p role="alert">{error}</p>}
      {results.isFetching && <p role="status">Ranking the indexed images on this server. The first search loads the model and can take about half a minute.</p>}
      {results.isError && <p role="alert">{results.error instanceof Error ? results.error.message : "The search could not be run."}</p>}
      {r && asked && (
        <div className="flex flex-col gap-1">
          <p className="italic text-muted-foreground">{r.label}</p>
          <p role="status">
            {r.scored === 0 ? "No image in this case is indexed yet, so nothing was ranked." : `Showing the ${n(r.shown)} highest ranked of ${n(r.scored)} indexed ${r.scored === 1 ? "image" : "images"} for "${r.query}".`}
            {r.truncated_words ? ` ${r.truncated_words}` : ""}
          </p>
          <ol aria-label="Images found" className="flex flex-col gap-2">
            {r.results.map((x) => {
              const first = x.copies[0]
              return (
                <li key={x.content_sha256} className="flex gap-2 rounded border p-1">
                  <span className="w-8 shrink-0 text-right font-mono" aria-label={`Rank ${x.rank}`}>{x.rank}</span>
                  {first && <ResultThumb caseId={caseId} fileUid={first.file_uid} name={first.filename} blur={blur} />}
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span>On {x.phones.join(", ")} ({n(x.copy_count)} {x.copy_count === 1 ? "copy" : "copies"})</span>
                    <ul className="flex flex-col gap-0.5">
                      {x.copies.map((c) => (
                        <li key={c.file_uid}>
                          <button type="button" className="underline underline-offset-2" onClick={() => onOpen(c.file_uid)}>{c.phone_label}: {c.filename}</button>
                          <span className="text-muted-foreground"> · {c.message_count ? `carried by ${n(c.message_count)} ${c.message_count === 1 ? "message" : "messages"}` : "carried by no message"}</span>
                        </li>
                      ))}
                    </ul>
                    {x.copy_count > x.copies.length && <span className="text-muted-foreground">{n(x.copy_count - x.copies.length)} more copies are not listed here.</span>}
                  </div>
                </li>
              )
            })}
          </ol>
          {r.shown < r.scored && (
            <Button size="sm" variant="outline" className="self-start" disabled={results.isFetching || asked.limit >= 200} onClick={() => setAsked({ query: asked.query, limit: Math.min(200, asked.limit + PAGE) })}>
              {asked.limit >= 200 ? "At most 200 are shown; refine the description" : `Show ${n(Math.min(PAGE, r.scored - r.shown, 200 - asked.limit))} more`}
            </Button>
          )}
        </div>
      )}
    </section>
  )
}
