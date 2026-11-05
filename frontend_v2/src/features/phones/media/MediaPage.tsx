import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { Fragment, useEffect, useRef, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { CollectBar } from "@/features/pattern/components/CollectBar"
import { recordPath } from "@/lib/record-links"
import { useCollectTargets } from "../collect-targets"
import { translationKey } from "../lib/translation-key"
import { BatchReading } from "./BatchReading"
import { ImageSearch } from "./ImageSearch"
import { OriginalsJobs } from "./OriginalsJobs"
import { MachineTextPrompt } from "./MachineTextPrompt"
import { useObjectUrl } from "./use-object-url"
import { EVERY_PHONE, mediaFilter, mediaIndexQuery, mediaPhoneIndexQuery, mediaWindowQuery, NONE } from "./media-queries"
import { THUMB_KEY, THUMB_SIZES, copyText, dayStart, fileListText, sizeWords, storedThumbSize, useArrowKeys, type ThumbSize } from "./media-tools"
import { acceptDerivedText, checkMediaDownload, requestOriginals, confirmDerivedText, correctDerivedText, getDerivedTexts, getMediaDetail, getMediaFacets, getPhones, getTranslations, requestDerivedText, translateDerivedText, type DerivedText, type MediaDownloadFacts, type MediaFilter, type MediaItem } from "../api"
import { noTimeWords } from "./no-time-words"
import { useMediaBlur } from "./use-media-blur"
import { SignificantNote } from "../ui/SignificantNote"
import { ScopeBar } from "../ui/ScopeBar"
import { ScopeCrossings } from "../ui/ScopeCrossings"
import { useUrlScope } from "../ui/use-phone-scope"

const n = (v: number) => v.toLocaleString("en-US")

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

function Thumb({ caseId, item, blur, height = "h-28" }: { caseId: string; item: MediaItem; blur: boolean; height?: string }) {
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
    <div ref={ref} className={`flex ${height} items-center justify-center overflow-hidden rounded bg-muted text-center text-[11px]`}>
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

const isAudio = (it: MediaItem) => /audio/i.test(it.category ?? "") || /\.(opus|ogg|oga|amr|m4a|aac|mp3|wav|caf|3ga|awb|flac)$/i.test(it.filename)

/** An audio file plays in the grid, loaded only when asked for. */
function TilePlayer({ caseId, item }: { caseId: string; item: MediaItem }) {
  const [on, setOn] = useState(false)
  const shown = useObjectUrl(caseId, item.file_uid, on)
  if (!on) return <Button size="sm" variant="outline" className="h-6 self-start px-2 text-[11px]" onClick={() => setOn(true)} aria-label={`Play ${item.filename}`}>Play</Button>
  if (shown && "error" in shown) return <span className="text-[11px]">{shown.error}</span>
  if (!shown) return <span role="status" className="text-[11px] text-muted-foreground">Loading the audio</span>
  return <audio controls autoPlay src={shown.url} aria-label={`Listen to ${item.filename}`} className="h-8 w-full" />
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

/** A machine translation of a finished transcript or image text (05 17.5), under the text it was made from: each
 * transcript segment keeps its time. Made by a local model; nothing is sent anywhere. */
function DerivedTranslation({ caseId, x }: { caseId: string; x: DerivedText }) {
  const qc = useQueryClient()
  const key = translationKey(caseId, x.id, x.effective_text ?? x.corrected_text ?? x.text)
  const q = useQuery({
    queryKey: key,
    queryFn: async () => (await getTranslations(caseId, "derived_text", [x.id]))[x.id] ?? null,
    refetchInterval: (query) => (query.state.data?.state === "queued" || query.state.data?.state === "running" ? 3000 : false),
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!(x.effective_text ?? x.text)) return null
  const t = q.data
  const ask = async () => {
    setBusy(true)
    setError(null)
    try {
      qc.setQueryData(key, await translateDerivedText(caseId, x.id))
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "The translation could not be asked for.")
    } finally {
      setBusy(false)
    }
  }
  const what = x.kind === "transcript" ? "transcript" : "text"
  return (
    <div className="flex flex-col gap-1" aria-label="Machine translation">
      {t?.state === "queued" && <p role="status">Waiting to be translated on this server.</p>}
      {t?.state === "running" && <p role="status">Being translated now.</p>}
      {t?.state === "failed" && <p role="alert">{t.error}</p>}
      {t?.state === "done" && t.outcome === "translated" && (
        <div className="flex flex-col gap-0.5 border-l-2 pl-2">
          {t.stale && <p className="font-medium">{t.stale_words}</p>}
          <p className="font-medium">Machine translation from {t.detected_language_name ?? "another language"}</p>
          <p className="italic text-muted-foreground">{t.label}</p>
          {t.segments.some((g) => g.start != null) ? (
            <ol className="flex flex-col gap-0.5">
              {t.segments.map((g, i) => <li key={i}><span className="font-mono text-muted-foreground">{fmtSeconds(g.start ?? 0)}</span> {g.text}</li>)}
            </ol>
          ) : (
            <p className="whitespace-pre-wrap">{t.text}</p>
          )}
          {t.language_words && <p className="text-muted-foreground">{t.language_words}</p>}
        </div>
      )}
      {t?.state === "done" && t.outcome !== "translated" && <p className="text-muted-foreground">{t.outcome_words} {t.language_words}</p>}
      {error && <p role="alert">{error}</p>}
      {!q.isLoading && (!t || t.state === "failed" || t.stale || t.asks_again) && (
        <Button size="sm" variant="outline" className="self-start" disabled={busy} onClick={() => void ask()}>
          {t?.stale ? `Translate the corrected ${what}` : t?.asks_again ? `Try translating this ${what} again` : `Translate this ${what}`}
        </Button>
      )}
    </div>
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
        <MachineTextPrompt caseId={caseId} onSettled={setSettled} onConfirmed={() => void onSaved()}
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
              {x.in_use === false && <p className="text-muted-foreground">Another reading of this file is the one searched and exported.</p>}
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
              <DerivedTranslation caseId={caseId} x={x} />
              <Review caseId={caseId} x={x} onSaved={() => client.invalidateQueries({ queryKey: ["phone-media-derived", caseId, fileUid] })} />
              {x.text || x.corrected_text ? <UseInAssessment caseId={caseId} x={x} filename={filename} onSaved={() => client.invalidateQueries({ queryKey: ["phone-media-derived", caseId, fileUid] })} /> : null}
            </>
          )}
        </div>
      ))}
    </section>
  )
}

/** The Media file panel: the file, its hashes and state, and every message that carried it. Also opened from Media
 * spread. */
export function Detail({ caseId, fileUid, onClose, onPrev = null, onNext = null, position }: {
  caseId: string; fileUid: string; onClose: () => void
  /** Previous and next file in the grid's order (also the left and right arrow keys); null at either end. */
  onPrev?: (() => void) | null; onNext?: (() => void) | null; position?: { at: number; of: number }
}) {
  useArrowKeys(!!(onPrev || onNext), onPrev, onNext)
  const d = useQuery({ queryKey: ["phone-media-detail", caseId, fileUid], queryFn: () => getMediaDetail(caseId, fileUid) })
  const file = useObjectUrl(caseId, fileUid, !!d.data && !d.data.missing)
  const x = d.data
  return (
    <aside aria-label="File" className="flex w-96 shrink-0 flex-col gap-2 overflow-auto border-l p-3 text-xs">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">File{position ? ` ${n(position.at)} of ${n(position.of)}` : ""}</h2>
        <span className="flex gap-1">
          {position && (
            <>
              <Button size="sm" variant="ghost" disabled={!onPrev} onClick={() => onPrev?.()} aria-keyshortcuts="ArrowLeft">Previous</Button>
              <Button size="sm" variant="ghost" disabled={!onNext} onClick={() => onNext?.()} aria-keyshortcuts="ArrowRight">Next</Button>
            </>
          )}
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
        </span>
      </div>
      {position && <p className="text-muted-foreground">Left and right arrow keys move too.</p>}
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

/** Media (03 section 8): every file on the phone, by category and state; the total is the phone summary's. */
export default function MediaPage() {
  const { id: caseId = "", extraction = "" } = useParams()
  const queryClient = useQueryClient()
  const [category, setCategory] = useState("")
  const [params, setParams] = useSearchParams()
  // a count on the Phone summary opens the files it counts (test P-4)
  const [state, setState] = useState(() => params.get("verification") ?? "")
  const open = params.get("file")
  const setOpen = (uid: string | null) => setParams((p) => {
    const next = new URLSearchParams(p)
    if (uid) next.set("file", uid)
    else next.delete("file")
    return next
  }, { replace: true })
  // Attachments (N) from a thread header (03 section 6.7, MD-1): the grid scoped to the files that thread carried
  const thread = params.get("thread")
  const threadTitle = params.get("thread_title")
  const back = params.get("back")
  const backTo = back && back.startsWith("/cases/") ? back : null
  const clearThread = () => setParams((p) => {
    const next = new URLSearchParams(p)
    for (const k of ["thread", "thread_title", "back"]) next.delete(k)
    return next
  }, { replace: true })
  const [phone, setPhone] = useState("")
  const [app, setApp] = useState("")
  const [pickedPerson, setPerson] = useState("")
  const [pickedFrom, setFromDay] = useState("")
  const [pickedTo, setToDay] = useState("")
  const [size, setSize] = useState<ThumbSize>(storedThumbSize)
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [note, setNote] = useState<string | null>(null)
  const [manual, setManual] = useState<string | null>(null)
  const [plan, setPlan] = useState<MediaDownloadFacts | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const blur = useMediaBlur(caseId)
  const [revealed, setRevealed] = useState<ReadonlySet<string>>(new Set())
  const [revealedPhones, setRevealedPhones] = useState<ReadonlySet<string>>(new Set())
  // an opened picture stays unblurred (03 section 8.3: blurred until opened); leaving the screen blurs them again
  useEffect(() => {
    if (open) setRevealed((r) => (r.has(open) ? r : new Set(r).add(open)))
  }, [open])
  const blurred = (it: MediaItem) => blur.on && !revealedPhones.has(it.extraction_id) && !revealed.has(it.file_uid)
  const significant = params.get("significant") === "1"
  const hasPosition = params.get("position") === "1"
  const setSignificant = (on: boolean) => setFilter(() => setParams((p) => {
    const next = new URLSearchParams(p)
    if (on) next.set("significant", "1")
    else next.delete("significant")
    return next
  }, { replace: true }))
  // a scope carried from another phone screen (07 4.5) fills the filters a person has not set here; the grid takes
  // one phone and one person, so more than that is stated, never dropped silently
  const carried = useUrlScope(caseId, { people: true, window: true, restore: false })
  const scopePerson = carried.scope.people[0]?.key ?? ""
  const scopePhone = carried.scope.phones.length === 1 ? carried.scope.phones[0].id : ""
  const scopeNote = [...carried.notApplied,
    ...(carried.scope.phones.length > 1 ? [`the ${n(carried.scope.phones.length)} phones chosen: this grid shows one phone or every phone`] : []),
    ...(carried.scope.people.length > 1 ? ["every person after the first"] : []),
    ...(carried.scope.people.length && carried.scope.mode !== "involving" ? ["the direction chosen"] : [])]
  const person = pickedPerson || scopePerson
  const fromDay = pickedFrom || (carried.scope.window?.from ?? "")
  const toDay = pickedTo || (carried.scope.window?.to ?? "")
  const from = dayStart(fromDay)
  const to = dayStart(toDay, 1)
  // the phone in the address, every phone in the case, or another phone of the case
  const onPhone = phone || scopePhone || extraction
  const filter: MediaFilter = mediaFilter(caseId, onPhone, thread, category, state, {
    ...(app ? { apps: [app] } : {}), ...(person ? { participants: [person] } : {}),
    ...(from ? { from_instant: from } : {}), ...(to ? { to_instant: to } : {}),
    ...(significant ? { significant_only: true } : {}),
    ...(hasPosition ? { has_position: true } : {}),
  })
  const filtered = !!(category || state || thread || app || person || from || to || significant || hasPosition)
  const scope = mediaFilter(caseId, onPhone, thread, "", "")
  const facets = useQuery({ queryKey: ["phone-media-facets", scope], queryFn: () => getMediaFacets(scope), enabled: !!caseId })
  const casePhones = useQuery({ queryKey: ["phones", caseId], queryFn: () => getPhones(caseId), enabled: !!caseId })
  const idx = useQuery({ ...mediaIndexQuery(filter), enabled: !!caseId })
  const all = useQuery({ ...mediaPhoneIndexQuery(caseId, onPhone), enabled: !!caseId })
  const pages = useInfiniteQuery({ ...mediaWindowQuery(filter), enabled: !!caseId })
  const items = pages.data?.pages.flatMap((p) => p.items) ?? []
  const shownPhones = [...new Map(items.map((i) => [i.extraction_id, { id: i.extraction_id, label: i.phone_label }])).values()]
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
  const at = open ? items.findIndex((it) => it.file_uid === open) : -1
  const onPrev = at > 0 ? () => setOpen(items[at - 1].file_uid) : null
  const onNext = at >= 0 && at < items.length - 1 ? () => setOpen(items[at + 1].file_uid)
    : at >= 0 && pages.hasNextPage ? () => {
      void pages.fetchNextPage().then((r) => {
        const next = (r.data?.pages.flatMap((p) => p.items) ?? [])[at + 1]
        if (next) setOpen(next.file_uid)
      })
    } : null
  const chosen = selected.size ? items.filter((it) => selected.has(it.file_uid)) : []
  const toggle = (uid: string) => setSelected((cur) => {
    const next = new Set(cur)
    if (next.has(uid)) next.delete(uid)
    else next.add(uid)
    return next
  })
  const copyList = () => {
    const list = chosen.length ? chosen : items
    const text = fileListText(list)
    const what = chosen.length ? `${n(list.length)} chosen ${list.length === 1 ? "file" : "files"}`
      : list.length < total ? `the ${n(list.length)} files loaded so far of ${n(total)}; scroll to load the rest first to copy them all` : `all ${n(list.length)} files`
    if (copyText(text)) { setManual(null); setNote(`Copied the list of ${what}.`) }
    else { setManual(text); setNote(`This browser did not allow copying. The list of ${what} is below to copy by hand.`) }
  }
  const downloadScope = [chosen[0]?.phone_label ?? items[0]?.phone_label, category && (category === NONE ? "uncategorised" : category), state && (state === NONE ? "unchecked" : state), selected.size ? `${n(selected.size)} chosen` : ""].filter(Boolean).join(" ") || "Selected files"
  const askDownload = async () => {
    setDownloadError(null)
    try { setPlan(await checkMediaDownload(filter, [...selected])) } catch (e) { setDownloadError(e instanceof Error ? e.message : "The download could not be checked.") }
  }
  const doDownload = async () => {
    setDownloading(true); setDownloadError(null)
    try {
      const job = await requestOriginals(filter, [...selected], downloadScope)
      await queryClient.invalidateQueries({ queryKey: ["phone-originals", caseId] })
      setPlan(null)
      setNote(`Making the zip of ${n(job.files_total)} ${job.files_total === 1 ? "file" : "files"}; you can leave this page. Its progress is below.`)
    } catch (e) { setDownloadError(e instanceof Error ? e.message : "The download could not be made.") } finally { setDownloading(false) }
  }
  const setFilter = (fn: () => void) => { fn(); setSelected(new Set()); setPlan(null) }
  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col gap-2 overflow-auto p-4">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-lg font-semibold">Media</h1>
          <Link className="text-sm underline" to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/media/spread`}>Media spread: the same file on other phones</Link>
        </div>
        <ScopeBar scope={carried.scope} onChange={carried.apply} presets={carried.presets} recent={carried.recent} notApplied={scopeNote}
          count={idx.data ? { shown: total, total, noun: total === 1 ? "file" : "files" } : null}>
          <ScopeCrossings caseId={caseId} scope={carried.scope} here="media" />
        </ScopeBar>
        {thread && (
          <div role="group" aria-label="Scope" className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-full border px-2 py-0.5">
              Files carried by the conversation {threadTitle ? `"${threadTitle}"` : "you came from"}
              <button type="button" className="ml-1 text-muted-foreground" aria-label="Remove the conversation scope" onClick={clearThread}>×</button>
            </span>
            {backTo && <Link className="underline underline-offset-2" to={backTo}>Back to the stream</Link>}
          </div>
        )}
        {idx.data && (
          <p role="status" className="text-sm">
            {n(total)} {total === 1 ? "file" : "files"}{filtered ? ` match the filter (of ${n(all.data?.total ?? total)}${phone ? "" : " on this phone"})` : ""}.
            {idx.data.missing ? ` ${n(idx.data.missing)} the report refers to are not in the production.` : ""}
            {noTimeWords(idx.data.no_time_count, idx.data.no_message_count)}
            {idx.data.outside_dates_no_time ? ` ${n(idx.data.outside_dates_no_time)} more have no time, so the dates leave them out.` : ""}
          </p>
        )}
        <SignificantNote
          caseId={caseId}
          on={significant}
          onChange={setSignificant}
          hiddenWords={significant && idx.data && all.data ? `${n(Math.max(0, all.data.total - total))} of ${n(all.data.total)} files are hidden.` : null}
        />
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-1" title="Only files whose own details, such as a photo's GPS tags, name a place">
            <input type="checkbox" checked={hasPosition} onChange={(e) => setFilter(() => setParams((p) => {
              const next = new URLSearchParams(p)
              if (e.target.checked) next.set("position", "1")
              else next.delete("position")
              return next
            }, { replace: true }))} />
            Has position
          </label>
          <label className="flex items-center gap-1">Phones
            <select value={phone} onChange={(e) => setFilter(() => { setPhone(e.target.value); setApp(""); setPerson("") })} className="max-w-48 rounded border bg-background px-1 py-0.5">
              <option value="">This phone</option>
              <option value={EVERY_PHONE}>Every phone in the case</option>
              {(casePhones.data?.phones ?? []).filter((p) => p.extraction_id !== extraction).map((p) => <option key={p.extraction_id} value={p.extraction_id}>{p.label}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">Category
            <select value={category} onChange={(e) => setFilter(() => setCategory(e.target.value))} className="rounded border bg-background px-1 py-0.5">
              <option value="">All</option>
              {Object.entries(all.data?.by_category ?? {}).map(([k, v]) => <option key={k} value={k === "Uncategorised" ? NONE : k}>{k} ({n(v)})</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">State
            <select value={state} onChange={(e) => setFilter(() => setState(e.target.value))} className="rounded border bg-background px-1 py-0.5">
              <option value="">All</option>
              {Object.entries(all.data?.verification ?? {}).map(([k, v]) => <option key={k} value={k === "unchecked" ? NONE : k}>{k} ({n(v)})</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">App
            <select value={app} onChange={(e) => setFilter(() => setApp(e.target.value))} className="rounded border bg-background px-1 py-0.5">
              <option value="">All</option>
              {(facets.data?.apps ?? []).map((a) => <option key={a.app} value={a.app}>{a.app} ({n(a.files)})</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">Person
            <select value={person} onChange={(e) => setFilter(() => setPerson(e.target.value))} className="max-w-48 rounded border bg-background px-1 py-0.5">
              <option value="">All</option>
              {(facets.data?.participants ?? []).map((p) => <option key={p.key} value={p.key}>{p.label} ({n(p.files)})</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">From
            <input type="date" aria-label="From" value={fromDay} onChange={(e) => setFilter(() => setFromDay(e.target.value))} className="rounded border bg-background px-1 py-0.5" />
          </label>
          <label className="flex items-center gap-1">To
            <input type="date" aria-label="To" value={toDay} onChange={(e) => setFilter(() => setToDay(e.target.value))} className="rounded border bg-background px-1 py-0.5" />
          </label>
          {(fromDay || toDay) && <span className="text-muted-foreground">Dates are whole days in UTC, by the time of the message that carried the file.</span>}
          <label className="flex items-center gap-1">Thumbnails
            <select value={size} onChange={(e) => { const v = e.target.value as ThumbSize; setSize(v); localStorage.setItem(THUMB_KEY, v) }} className="rounded border bg-background px-1 py-0.5">
              {(Object.keys(THUMB_SIZES) as ThumbSize[]).map((k) => <option key={k} value={k}>{THUMB_SIZES[k].label}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={blur.on} onChange={(e) => blur.choose(e.target.checked)} />
            Blur pictures until opened
          </label>
          {blur.caseDefault && <span className="text-muted-foreground">Case default: {blur.caseDefault.default_on ? "on" : "off"}. {blur.caseDefault.words}</span>}
          {blur.on && shownPhones.map((p) => (
            <button key={p.id} type="button" className="underline underline-offset-2" aria-pressed={revealedPhones.has(p.id)}
              onClick={() => setRevealedPhones((r) => { const next = new Set(r); if (!next.delete(p.id)) next.add(p.id); return next })}>
              {revealedPhones.has(p.id) ? `Blur ${p.label}'s pictures again` : `Show ${p.label}'s pictures`}
            </button>
          ))}
          {blur.error && <span role="alert">{blur.error}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs" aria-label="Files to copy or download">
          <span>{selected.size ? `${n(selected.size)} chosen.` : "Choose files with their boxes, or act on every file the filter shows."}</span>
          {selected.size > 0 && <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear the choice</Button>}
          <Button size="sm" variant="outline" onClick={copyList} disabled={!items.length}>Copy file list</Button>
          <Button size="sm" variant="outline" onClick={() => void askDownload()} disabled={!total || downloading}>Download originals</Button>
          {chosen.length > 0 && (
            <CollectBar caseId={caseId} noun={chosen.length === 1 ? "file" : "files"} origin="phone-media"
              links={chosen.map((it) => ({ target_type: "phone_file" as const, target_id: it.file_uid, label: it.filename, source_anchor: { kind: "phone_file", file_uid: it.file_uid } }))} />
          )}
        </div>
        {note && <p role="status" className="text-xs">{note}</p>}
        {manual && <textarea aria-label="File list to copy" readOnly className="h-32 w-full rounded border p-1 font-mono text-[11px]" value={manual} onFocus={(e) => e.currentTarget.select()} />}
        {plan && (
          <div className="flex flex-col gap-1 rounded border p-2 text-xs" aria-label="Download originals">
            {plan.refusal ? <p role="alert">{plan.refusal}</p> : (
              <>
                <p>
                  {n(plan.count)} {plan.count === 1 ? "file" : "files"}, {sizeWords(plan.bytes)}, as a zip with manifest.csv of every file's hashes.
                  {plan.not_in_production ? ` ${n(plan.not_in_production)} the report names are not in the production; the manifest lists them.` : ""}
                </p>
                <div className="flex gap-1">
                  <Button size="sm" disabled={downloading} onClick={() => void doDownload()}>{downloading ? "Starting the zip" : "Make the zip"}</Button>
                  <Button size="sm" variant="ghost" disabled={downloading} onClick={() => setPlan(null)}>Cancel</Button>
                </div>
              </>
            )}
            {plan.refusal && <Button size="sm" variant="ghost" className="self-start" onClick={() => setPlan(null)}>Close</Button>}
          </div>
        )}
        {downloadError && <p role="alert" className="text-xs">{downloadError}</p>}
        <OriginalsJobs caseId={caseId} />
        {pages.isError && <p role="alert" className="text-sm">The files could not be loaded.</p>}
        <BatchReading caseId={caseId} filter={filter} scopeWords={[category && `${category === NONE ? "uncategorised" : category} files`, state && `${state === NONE ? "unchecked" : state} files`].filter(Boolean).join(", ") || (phone === EVERY_PHONE ? "every phone in the case" : "this phone")} />
        <ImageSearch caseId={caseId} blur={blur.on} onOpen={setOpen} />
        <ul aria-label="Files" className={`grid ${THUMB_SIZES[size].grid} gap-2`}>
          {items.map((it) => (
            <li key={it.file_uid} className="relative">
              <input type="checkbox" aria-label={`Choose ${it.filename}`} checked={selected.has(it.file_uid)} onChange={() => toggle(it.file_uid)}
                className="absolute left-2 top-2 z-10" />
              <button type="button" onClick={() => setOpen(it.file_uid)} className="flex w-full flex-col gap-1 rounded border p-1 text-left text-[11px] hover:bg-muted/40">
                <Thumb caseId={caseId} item={it} blur={blurred(it)} height={THUMB_SIZES[size].height} />
                <span className="truncate font-medium">{it.filename}</span>
                <span className="truncate text-muted-foreground">{it.phone_label} · {it.taken_or_sent.full}</span>
                <span className="truncate">{it.verification_words}{it.message_count ? ` · ${n(it.message_count)} ${it.message_count === 1 ? "message" : "messages"}` : ""}</span>
              </button>
              {(it.machine_text ?? []).map((m) => (
                <span key={m.kind} title={m.words ?? undefined} data-origin={m.state} className={`block truncate px-1 text-[11px] ${m.state === "machine" ? "italic text-muted-foreground" : ""}`}>
                  {m.kind === "transcript" ? "Transcript" : "Text read"}: {m.short}
                </span>
              ))}
              {isAudio(it) && !it.missing && <div className="px-1 pt-1"><TilePlayer caseId={caseId} item={it} /></div>}
            </li>
          ))}
        </ul>
        <div ref={sentinel} />
        {pages.isFetchingNextPage && <p role="status" className="text-xs">Loading more files ({n(items.length)} of {n(total)} shown).</p>}
      </div>
      {open && <Detail caseId={caseId} fileUid={open} onClose={() => setOpen(null)} onPrev={onPrev} onNext={onNext}
        position={at >= 0 ? { at: at + 1, of: total } : undefined} />}
    </div>
  )
}
