import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { Fragment, useEffect, useRef, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { recordPath } from "@/lib/record-links"
import { useCollectTargets } from "../collect-targets"
import { MachineTextPrompt } from "./MachineTextPrompt"
import { useObjectUrl } from "./use-object-url"
import { acceptDerivedText, confirmDerivedText, correctDerivedText, getDerivedTexts, getMediaDetail, getMediaIndex, getMediaWindow, requestDerivedText, type DerivedText, type MediaFilter, type MediaItem } from "../api"

const n = (v: number) => v.toLocaleString("en-US")
const WINDOW = 200
const BLUR_KEY = "loupe.media.blur"

const CONVERTED_WORDS = "Playing a converted copy. The original file is unchanged."

/** Plays a phone audio or video file. When the browser cannot play the original (an error, or a video that loads
 * with no picture: 03 20.5 measured H.263, MPEG-4 Part 2 and HEVC playing sound only), it asks once for a
 * converted copy made on the server and says so; the original stays the one saved and hashed. */
function MediaPlayer({ caseId, fileUid, original }: { caseId: string; fileUid: string; original: { url: string; type: string } }) {
  const [wantConverted, setWantConverted] = useState(false)
  const converted = useObjectUrl(caseId, fileUid, wantConverted, "converted")
  const shown = wantConverted && converted && "url" in converted ? converted : wantConverted ? null : original
  const fallBack = () => setWantConverted(true)
  const isVideo = (shown ?? original).type.startsWith("video/")
  return (
    <div className="flex flex-col gap-1">
      {shown ? (
        isVideo ? (
          <video
            key={shown.url}
            src={shown.url}
            controls
            className="max-h-80"
            onError={shown === original ? fallBack : undefined}
            onLoadedData={shown === original ? (e) => { if (e.currentTarget.videoWidth === 0) fallBack() } : undefined}
          />
        ) : (
          <audio key={shown.url} src={shown.url} controls onError={shown === original ? fallBack : undefined} />
        )
      ) : converted && "error" in converted ? (
        <p role="alert">This browser cannot play the original. {converted.error}</p>
      ) : (
        <p role="status">This browser cannot play the original; making a converted copy.</p>
      )}
      {shown && shown !== original && <p role="note">{CONVERTED_WORDS}</p>}
      {wantConverted && <a className="underline" href={original.url} download>Save the original</a>}
    </div>
  )
}

function Thumb({ caseId, item, blur }: { caseId: string; item: MediaItem; blur: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === "undefined") return
    const io = new IntersectionObserver((e) => e.some((x) => x.isIntersecting) && setSeen(true), { rootMargin: "200px" })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  const isImage = (item.category ?? "").toLowerCase().includes("image") || /\.(jpe?g|png|gif|webp|heic|bmp)$/i.test(item.filename)
  const shown = useObjectUrl(caseId, item.file_uid, seen && isImage && !item.missing, "thumbnail")
  return (
    <div ref={ref} className="flex h-28 items-center justify-center overflow-hidden rounded bg-muted text-center text-[11px]">
      {item.missing ? (
        <span className="px-2">The report refers to a file that is not in the production.</span>
      ) : shown && "url" in shown ? (
        <img src={shown.url} alt={item.filename} className={`h-full w-full object-cover ${blur ? "blur-md" : ""}`} />
      ) : shown && "error" in shown ? (
        <span className="px-2">{shown.error}</span>
      ) : (
        <span className="px-2 text-muted-foreground">{item.category ?? "File"}</span>
      )}
    </div>
  )
}

/** Exactly what made a machine text (05 17.4): model id, version, the weights' hash and the input's hash, in
 * full. Older texts that did not record it say so. */
function MadeBy({ x }: { x: DerivedText }) {
  if (!x.model_id) return <p className="text-xs text-muted-foreground">The model's exact weights were not recorded for this text.</p>
  const rows: [string, string][] = [
    ["Model", `${x.model_id} (${x.model_version ?? "version not recorded"})`],
    ["Weights SHA-256", x.weights_sha256 ?? "not recorded"],
    ["File read (SHA-256)", x.input_sha256 ?? "not recorded"],
  ]
  if (x.sniffed_container) rows.push(["File kind, from its contents", x.sniffed_container])
  if (x.language) rows.push(["Language detected", x.language])
  if (x.parameters) rows.push(["Settings", Object.entries(x.parameters).map(([k, v]) => `${k}: ${String(v)}`).join("; ")])
  return (
    <details className="text-xs text-muted-foreground">
      <summary className="cursor-pointer">What made this text</summary>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-2 gap-y-0.5">
        {rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd className="break-all font-mono">{v}</dd></Fragment>)}
      </dl>
    </details>
  )
}

/** A person checks machine text (07 4.6, M-6): confirm it stands, or correct it with a reason. The machine original
 * stays shown under a correction; the corrected text is the one searched and quoted. */
function Review({ caseId, x, onSaved }: { caseId: string; x: DerivedText; onSaved: () => Promise<unknown> }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      setEditing(false)
      await onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : "The change could not be saved.")
    } finally {
      setBusy(false)
    }
  }
  const what = x.kind === "transcript" ? "the audio" : "the image"
  return (
    <div className="flex flex-col gap-1">
      {!editing && (
        <div className="flex flex-wrap gap-1">
          {x.origin?.state !== "confirmed" && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => confirmDerivedText(caseId, x.id))}>
              I checked it against {what}: confirm
            </Button>
          )}
          <Button size="sm" variant="outline" disabled={busy} onClick={() => { setDraft(x.effective_text ?? x.text ?? ""); setReason(""); setEditing(true) }}>
            Correct this text
          </Button>
        </div>
      )}
      {editing && (
        <form className="flex flex-col gap-1" onSubmit={(e) => { e.preventDefault(); void run(() => correctDerivedText(caseId, x.id, draft, reason)) }}>
          <label className="flex flex-col gap-0.5">Corrected text
            <textarea className="rounded border p-1" rows={4} value={draft} onChange={(e) => setDraft(e.target.value)} />
          </label>
          <label className="flex flex-col gap-0.5">Reason, in your own words
            <input className="rounded border p-1" value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <p className="text-muted-foreground">The machine text stays shown beside your correction. Your correction is the text searched and quoted.</p>
          <div className="flex gap-1">
            <Button size="sm" type="submit" disabled={busy || !draft.trim() || !reason.trim()}>Save correction</Button>
            <Button size="sm" type="button" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </form>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

function MachineBody({ x }: { x: DerivedText }) {
  return x.segments.length ? (
    <ol className="flex flex-col gap-0.5">
      {x.segments.map((s, i) => <li key={i}><span className="font-mono text-muted-foreground">{fmtSeconds(s.start)}</span> {s.text}</li>)}
    </ol>
  ) : x.text ? (
    <p className="whitespace-pre-wrap">{x.text}</p>
  ) : (
    <p>No text was found.</p>
  )
}

/** CO-18 and M-7: machine text used in a dossier assessment. An unconfirmed text is shown with its original first
 * (confirm it, or keep it marked); the assessment is stored as AI-assisted, "Read by <model>, accepted by <name>". */
function UseInAssessment({ caseId, x, filename, onSaved }: { caseId: string; x: DerivedText; filename: string | null; onSaved: () => Promise<unknown> }) {
  const [open, setOpen] = useState(false)
  const [dossier, setDossier] = useState("")
  const [category, setCategory] = useState("Statement")
  const [settled, setSettled] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const targets = useCollectTargets(open ? caseId : "")
  const dossiers = targets.targets.filter((t) => t.kind === "dossier")
  const needsAnswer = !x.origin?.confirmed
  if (!open) return <Button size="sm" variant="outline" className="self-start" onClick={() => setOpen(true)}>Use in a dossier assessment</Button>
  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await acceptDerivedText(caseId, x.id, dossier, category.trim())
      setDone(r.read_by ?? "Added.")
      await onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : "The assessment could not be saved.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-col gap-1 rounded border p-2">
      {needsAnswer && (
        <MachineTextPrompt caseId={caseId} onSettled={setSettled}
          facts={{ total: 1, unconfirmed: 1, items_cap: 1, items: [{ id: x.id, file_uid: x.file_uid, kind: x.kind, filename, words: x.origin?.words ?? x.label }] }} />
      )}
      <label className="flex flex-col gap-0.5">Dossier
        <select className="rounded border p-1" value={dossier} onChange={(e) => setDossier(e.target.value)}>
          <option value="">Choose a dossier</option>
          {dossiers.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
      </label>
      {targets.note && <p className="text-muted-foreground">{targets.note}</p>}
      <label className="flex flex-col gap-0.5">Assessment category
        <input className="rounded border p-1" value={category} maxLength={128} onChange={(e) => setCategory(e.target.value)} />
      </label>
      <p className="text-muted-foreground">Stored as AI-assisted, with the model that read it and your name.</p>
      {done ? <p role="status">Added to the dossier: {done}</p> : (
        <div className="flex gap-1">
          <Button size="sm" disabled={busy || !dossier || !category.trim() || (needsAnswer && !settled)} onClick={save}>Add to the assessment</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

const fmtSeconds = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`

/** Machine-generated text (03 8.3, M-3): asked for here, made by a model on the server, always shown with its
 * label under the original. Nothing is sent anywhere. */
export function DerivedTexts({ caseId, fileUid, category, filename = null }: { caseId: string; fileUid: string; category: string | null; filename?: string | null }) {
  const client = useQueryClient()
  // A file the report left uncategorised may be read either way; its contents decide (05 17.4 point 1).
  const uncategorised = !category || category === "Uncategorized"
  const kinds: ("ocr" | "transcript")[] = category === "Image" ? ["ocr"] : category === "Audio" || category === "Video" ? ["transcript"] : uncategorised ? ["ocr", "transcript"] : []
  const q = useQuery({
    queryKey: ["phone-media-derived", caseId, fileUid],
    queryFn: () => getDerivedTexts(caseId, fileUid),
    refetchInterval: (query) => (query.state.data?.items.some((x) => x.state === "queued" || x.state === "running") ? 3000 : false),
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const items = q.data?.items ?? []
  const waiting = items.some((x) => x.state === "queued" || x.state === "running")
  const ask = async (kind: "ocr" | "transcript") => {
    setBusy(true)
    setError(null)
    try {
      await requestDerivedText(caseId, fileUid, kind)
      await client.invalidateQueries({ queryKey: ["phone-media-derived", caseId, fileUid] })
    } catch (e) {
      setError(e instanceof Error ? e.message : "The request could not be made.")
    } finally {
      setBusy(false)
    }
  }
  if (!kinds.length && !items.length) return null
  return (
    <section aria-label="Machine-generated text" className="flex flex-col gap-1">
      <h3 className="font-medium">Machine-generated text</h3>
      {uncategorised && kinds.length > 0 && <p className="text-muted-foreground">The report does not say what kind of file this is; its contents decide which reading works.</p>}
      {kinds.map((kind) => (
        <Button key={kind} size="sm" variant="outline" onClick={() => ask(kind)} disabled={busy || waiting} className="self-start">
          {kind === "ocr" ? "Read text in this image" : "Transcribe this audio"}
        </Button>
      ))}
      <p className="text-muted-foreground">Made by a model on this server; nothing is sent anywhere. Until a person confirms or corrects it, it is marked as not checked.</p>
      {error && <p role="alert">{error}</p>}
      {items.map((x) => (
        <div key={x.id} className="flex flex-col gap-1 rounded border p-2">
          {x.state === "queued" && <p role="status">Waiting to be read.</p>}
          {x.state === "running" && <p role="status">Being read now.</p>}
          {x.state === "failed" && <p role="alert">{x.error}</p>}
          {x.state === "done" && (
            <>
              {x.origin?.words && <p className="font-medium" data-origin={x.origin.state}>{x.origin.words}</p>}
              {x.corrected_text != null ? (
                <>
                  <p className="text-muted-foreground">Corrected text, used in search and quotes:</p>
                  <p className="whitespace-pre-wrap">{x.corrected_text}</p>
                  <details open className="text-muted-foreground">
                    <summary className="cursor-pointer">Machine original, kept as it was read</summary>
                    <p className="italic">{x.label}</p>
                    <MachineBody x={x} />
                  </details>
                </>
              ) : (
                <>
                  <p className="italic text-muted-foreground">{x.label}</p>
                  <MachineBody x={x} />
                </>
              )}
              {x.provider_words && <p className="text-muted-foreground">{x.provider_words}</p>}
              <MadeBy x={x} />
              <Review caseId={caseId} x={x} onSaved={() => client.invalidateQueries({ queryKey: ["phone-media-derived", caseId, fileUid] })} />
              {x.text || x.corrected_text ? <UseInAssessment caseId={caseId} x={x} filename={filename} onSaved={() => client.invalidateQueries({ queryKey: ["phone-media-derived", caseId, fileUid] })} /> : null}
            </>
          )}
        </div>
      ))}
    </section>
  )
}

function Detail({ caseId, fileUid, onClose }: { caseId: string; fileUid: string; onClose: () => void }) {
  const d = useQuery({ queryKey: ["phone-media-detail", caseId, fileUid], queryFn: () => getMediaDetail(caseId, fileUid) })
  const file = useObjectUrl(caseId, fileUid, !!d.data && !d.data.missing)
  const x = d.data
  return (
    <aside aria-label="File" className="flex w-96 shrink-0 flex-col gap-2 overflow-auto border-l p-3 text-xs">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">File</h2>
        <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
      </div>
      {d.isLoading && <p role="status">Loading the file.</p>}
      {d.isError && <p role="alert">This file could not be loaded.</p>}
      {x && (
        <>
          <p className="break-all font-medium">{x.local_path ?? "No path given in the report"}</p>
          {x.missing ? (
            <p role="note">{x.missing_words}</p>
          ) : file && "url" in file ? (
            file.type.startsWith("image/") ? <img src={file.url} alt={x.local_path ?? "file"} className="max-h-80 object-contain" />
              : file.type.startsWith("video/") || file.type.startsWith("audio/") ? <MediaPlayer caseId={caseId} fileUid={fileUid} original={file} />
              : <a className="underline" href={file.url} download>Save the original</a>
          ) : file && "error" in file ? (
            <p role="alert">{file.error}</p>
          ) : (
            <p role="status">Loading the file.</p>
          )}
          {!x.missing && <DerivedTexts caseId={caseId} fileUid={fileUid} category={x.category} filename={(x.local_path ?? "").replace(/\\/g, "/").split("/").pop() || null} />}
          <p>{x.verification_words}</p>
          {x.deleted_state && <p>Deleted state: {x.deleted_state}</p>}
          <dl className="grid grid-cols-[auto_1fr] gap-x-2">
            {Object.entries(x.hashes).filter(([, v]) => v).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="break-all font-mono">{v}</dd></div>
            ))}
          </dl>
          <h3 className="font-medium">Carried by {n(x.message_count)} {x.message_count === 1 ? "message" : "messages"}</h3>
          <ul className="flex flex-col gap-1">
            {x.messages.map((m) => (
              <li key={m.record_uid}>
                <Link className="underline" to={recordPath(caseId, m.message_record_uid)}>{m.kind === "call" ? "The call" : "The message"}{m.instant ? ` at ${new Date(m.instant).toISOString().slice(0, 16).replace("T", " ")} UTC` : ""}</Link>
                <span className="text-muted-foreground"> (found by {m.mechanism_words})</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  )
}

/** The filter value for files with no category or no check: sent as "" so the server matches the empty ones. */
const NONE = "__none__"

/** Media (03 section 8): every file on the phone, by category and state; the total is the phone summary's. */
export default function MediaPage() {
  const { id: caseId = "", extraction = "" } = useParams()
  const [category, setCategory] = useState("")
  const [state, setState] = useState("")
  const [params, setParams] = useSearchParams()
  const open = params.get("file")
  const setOpen = (uid: string | null) => setParams((p) => {
    const next = new URLSearchParams(p)
    if (uid) next.set("file", uid)
    else next.delete("file")
    return next
  }, { replace: true })
  const [blur, setBlur] = useState(() => localStorage.getItem(BLUR_KEY) !== "off")
  const filter: MediaFilter = { case_id: caseId, phones: [extraction], ...(category ? { categories: [category === NONE ? "" : category] } : {}), ...(state ? { verification: [state === NONE ? "" : state] } : {}) }
  const idx = useQuery({ queryKey: ["phone-media-index", filter], queryFn: () => getMediaIndex(filter), enabled: !!caseId })
  const all = useQuery({ queryKey: ["phone-media-index", caseId, extraction], queryFn: () => getMediaIndex({ case_id: caseId, phones: [extraction] }), enabled: !!caseId })
  const pages = useInfiniteQuery({
    queryKey: ["phone-media-window", filter],
    queryFn: ({ pageParam }) => getMediaWindow(filter, pageParam, WINDOW),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.items.length === WINDOW ? last.offset + WINDOW : undefined),
    enabled: !!caseId,
  })
  const items = pages.data?.pages.flatMap((p) => p.items) ?? []
  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el || typeof IntersectionObserver === "undefined") return
    const io = new IntersectionObserver((e) => {
      if (e.some((x) => x.isIntersecting) && pages.hasNextPage && !pages.isFetchingNextPage) void pages.fetchNextPage()
    }, { rootMargin: "600px" })
    io.observe(el)
    return () => io.disconnect()
  }, [pages])
  const total = idx.data?.total ?? 0
  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col gap-2 overflow-auto p-4">
        <h1 className="text-lg font-semibold">Media</h1>
        {idx.data && (
          <p role="status" className="text-sm">
            {n(total)} {total === 1 ? "file" : "files"}{category || state ? ` match the filter (of ${n(all.data?.total ?? total)})` : ""}.
            {idx.data.missing ? ` ${n(idx.data.missing)} the report refers to are not in the production.` : ""}
            {idx.data.no_time_count ? ` ${n(idx.data.no_time_count)} were carried by no message and have no time; they are listed at the end.` : ""}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-1">Category
            <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded border bg-background px-1 py-0.5">
              <option value="">All</option>
              {Object.entries(all.data?.by_category ?? {}).map(([k, v]) => <option key={k} value={k === "Uncategorised" ? NONE : k}>{k} ({n(v)})</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">State
            <select value={state} onChange={(e) => setState(e.target.value)} className="rounded border bg-background px-1 py-0.5">
              <option value="">All</option>
              {Object.entries(all.data?.verification ?? {}).map(([k, v]) => <option key={k} value={k === "unchecked" ? NONE : k}>{k} ({n(v)})</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={blur} onChange={(e) => { setBlur(e.target.checked); localStorage.setItem(BLUR_KEY, e.target.checked ? "on" : "off") }} />
            Blur pictures until opened
          </label>
        </div>
        {pages.isError && <p role="alert" className="text-sm">The files could not be loaded.</p>}
        <ul aria-label="Files" className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-2">
          {items.map((it) => (
            <li key={it.file_uid}>
              <button type="button" onClick={() => setOpen(it.file_uid)} className="flex w-full flex-col gap-1 rounded border p-1 text-left text-[11px] hover:bg-muted/40">
                <Thumb caseId={caseId} item={it} blur={blur && open !== it.file_uid} />
                <span className="truncate font-medium">{it.filename}</span>
                <span className="truncate text-muted-foreground">{it.phone_label} · {it.taken_or_sent.full}</span>
                <span className="truncate">{it.verification_words}{it.message_count ? ` · ${n(it.message_count)} ${it.message_count === 1 ? "message" : "messages"}` : ""}</span>
              </button>
            </li>
          ))}
        </ul>
        <div ref={sentinel} />
        {pages.isFetchingNextPage && <p role="status" className="text-xs">Loading more files ({n(items.length)} of {n(total)} shown).</p>}
      </div>
      {open && <Detail caseId={caseId} fileUid={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
