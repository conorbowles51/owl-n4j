import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { recordPath } from "@/lib/record-links"
import { getMediaSpreadIndex, getMediaSpreadWindow, type SpreadCopy, type SpreadFilter, type SpreadGroup, type SpreadPhone } from "../api"
import { Detail } from "./MediaPage"
import { useObjectUrl } from "./use-object-url"

const n = (v: number) => v.toLocaleString("en-US")
const PAGE = 50
const ROLE_WORDS: Record<string, string> = { sent: "sent", received: "received", direction_unknown: "direction not recorded" }

const roleText = (roles: string[]) => (roles.length ? roles.map((r) => ROLE_WORDS[r] ?? r).join(" and ") : "not carried by a message")

function GroupThumb({ caseId, g }: { caseId: string; g: SpreadGroup }) {
  const isImage = (g.category ?? "").toLowerCase().includes("image") || /\.(jpe?g|png|gif|webp|heic|bmp)$/i.test(g.filename)
  const shown = useObjectUrl(caseId, g.thumbnail_file_uid, !!g.thumbnail_file_uid && isImage, "thumbnail")
  return (
    <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded bg-muted text-center text-[11px]">
      {!g.thumbnail_file_uid ? (
        <span className="px-1">No copy of this file is in the production.</span>
      ) : shown && "url" in shown ? (
        <img src={shown.url} alt={g.filename} className="h-full w-full object-cover" />
      ) : shown && "error" in shown ? (
        <span className="px-1">{shown.error}</span>
      ) : (
        <span className="px-1 text-muted-foreground">{g.category ?? "File"}</span>
      )}
    </div>
  )
}

function CopyLine({ caseId, c, onOpen }: { caseId: string; c: SpreadCopy; onOpen: (uid: string) => void }) {
  return (
    <li className="flex flex-col gap-0.5 rounded border p-1">
      <button type="button" className="self-start break-all text-left underline" onClick={() => onOpen(c.file_uid)}>
        Open {c.filename}
      </button>
      <span className="text-muted-foreground">Included because: {c.included_because.join("; ")}.</span>
      {c.missing && <span>{c.verification_words}</span>}
      {c.times.map((t, i) => (
        <span key={i}>{t.full} <span className="text-muted-foreground">({t.source_words}{t.has_offset ? "" : "; not used for the order"})</span></span>
      ))}
      {c.messages.map((m) => (
        <span key={m.message_record_uid}>
          <Link className="underline" to={recordPath(caseId, m.message_record_uid)}>{m.role === "sent" ? "Sent" : m.role === "received" ? "Received" : "Carried"}{m.app ? ` on ${m.app}` : ""}</Link>
          {m.line ? `: ${m.line}` : ""}{m.deleted ? " (message marked deleted)" : ""}
        </span>
      ))}
      {c.note && <span role="note">{c.note}</span>}
      {c.camera && <span>Camera in the photo's EXIF: {[c.camera.make, c.camera.model].filter(Boolean).join(" ")}</span>}
      {c.camera_original_words && <span className="font-medium" data-candidate={String(c.camera_original_candidate)}>{c.camera_original_words}</span>}
      {c.place && <span>{c.place.words} (source: {c.place.source})</span>}
    </li>
  )
}

function PhoneRow({ caseId, p, onOpen }: { caseId: string; p: SpreadPhone; onOpen: (uid: string) => void }) {
  return (
    <li className="flex flex-col gap-1">
      <span>
        <span className="font-medium">{p.position != null ? `${p.position}. ` : ""}{p.phone_label}</span>
        {": "}
        {p.earliest ? <>first held {p.earliest.full} <span className="text-muted-foreground">({p.earliest.source_words})</span></> : "no time with a time zone to place it in the order"}
        {"; "}{roleText(p.roles)}
        {p.camera_original_candidate ? "; holds a camera original candidate" : ""}
        {p.copy_count > 1 ? `; ${n(p.copy_count)} copies` : ""}
      </span>
      <ul className="ml-4 flex flex-col gap-1">
        {p.copies.map((c) => <CopyLine key={c.file_uid} caseId={caseId} c={c} onOpen={onOpen} />)}
      </ul>
      {p.copies_words && <span role="note" className="ml-4">{p.copies_words}</span>}
    </li>
  )
}

/** Media spread (05 section 11): files whose exact copies are on two or more phones of the case, the order each phone
 * came to hold them, sent and received, camera original candidates and flags. Opening a copy opens the file panel. */
export default function MediaSpreadPage() {
  const { id: caseId = "", extraction = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const [onlyThis, setOnlyThis] = useState(true)
  const [common, setCommon] = useState<"all" | "hide" | "only">("all")
  const [offset, setOffset] = useState(0)
  const open = params.get("file")
  const setOpen = (uid: string | null) => setParams((prev) => {
    const next = new URLSearchParams(prev)
    if (uid) next.set("file", uid)
    else next.delete("file")
    return next
  }, { replace: true })
  const filter: SpreadFilter = { phones: onlyThis && extraction ? [extraction] : [], common }
  const idx = useQuery({ queryKey: ["phone-media-spread-index", caseId], queryFn: () => getMediaSpreadIndex(caseId), enabled: !!caseId })
  const win = useQuery({ queryKey: ["phone-media-spread-window", caseId, filter, offset], queryFn: () => getMediaSpreadWindow(caseId, filter, offset, PAGE), enabled: !!caseId })
  const total = win.data?.total ?? 0
  const items = win.data?.items ?? []
  const thisLabel = idx.data?.by_phone.find((p) => p.extraction_id === extraction)?.label
  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col gap-2 overflow-auto p-4 text-sm">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-lg font-semibold">Media spread</h1>
          <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/media`}>Back to Media</Link>
        </div>
        {idx.data && (
          <p role="status">
            {n(idx.data.total_groups)} {idx.data.total_groups === 1 ? "file is" : "files are"} on two or more of the case's {n(idx.data.case_phone_count)} phones ({n(idx.data.total_copies)} copies).
            {idx.data.common_file_groups ? ` ${n(idx.data.common_file_groups)} of them are common files, on more than half the phones.` : ""}
            {idx.data.sha256_disagreement_groups ? ` ${n(idx.data.sha256_disagreement_groups)} have equal MD5 but different SHA-256 values.` : ""}
          </p>
        )}
        {idx.data && <p className="text-xs text-muted-foreground">{idx.data.population_words}</p>}
        {idx.data && <p className="text-xs text-muted-foreground">{idx.data.clock_words}</p>}
        {idx.data && idx.data.by_pair.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer">Files shared by each pair of phones</summary>
            <ul aria-label="Pairs of phones">
              {idx.data.by_pair.map((p) => <li key={`${p.a.extraction_id}-${p.b.extraction_id}`}>{p.a.label} and {p.b.label}: {n(p.groups)}</li>)}
            </ul>
          </details>
        )}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={onlyThis} onChange={(e) => { setOnlyThis(e.target.checked); setOffset(0) }} />
            Only files on {thisLabel ?? "this phone"}
          </label>
          <label className="flex items-center gap-1">Common files
            <select value={common} onChange={(e) => { setCommon(e.target.value as "all" | "hide" | "only"); setOffset(0) }} className="rounded border bg-background px-1 py-0.5">
              <option value="all">Show</option>
              <option value="hide">Leave out</option>
              <option value="only">Only common files</option>
            </select>
          </label>
        </div>
        {win.isLoading && <p role="status">Loading.</p>}
        {(win.isError || idx.isError) && <p role="alert">The media spread could not be loaded.</p>}
        {win.data && (
          <p role="status" className="text-xs">
            {total === 0 ? "No files match." : `Showing ${n(offset + 1)} to ${n(offset + items.length)} of ${n(total)} ${total === 1 ? "file" : "files"}.`}
          </p>
        )}
        <ul aria-label="Files on several phones" className="flex flex-col gap-3">
          {items.map((g) => (
            <li key={g.group_key} className="flex gap-3 rounded border p-2 text-xs">
              <GroupThumb caseId={caseId} g={g} />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="break-all font-medium">{g.filename}</span>
                <span>On {n(g.phone_count)} phones, {n(g.copy_count)} {g.copy_count === 1 ? "copy" : "copies"}; identical by MD5.</span>
                {g.common_words && <span role="note" className="font-medium">{g.common_words}</span>}
                {g.sha256_words && <span role="note" className="font-medium">{g.sha256_words}</span>}
                <ol aria-label="Order the phones held it" className="flex flex-col gap-1">
                  {g.phones.map((p) => <PhoneRow key={p.extraction_id} caseId={caseId} p={p} onOpen={setOpen} />)}
                </ol>
              </div>
            </li>
          ))}
        </ul>
        {total > PAGE && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
            <Button size="sm" variant="outline" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
          </div>
        )}
      </div>
      {open && <Detail caseId={caseId} fileUid={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
