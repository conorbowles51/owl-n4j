import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { CopyButton } from "@/components/ui/copy-button"
import { htmlEscape } from "@/lib/copy-text"
import { failureText, getRecord, revealValue } from "../api"
import type { RecordDetail, RecordFieldData } from "../schemas"
import { DockedPanel } from "../ui/DockedPanel"
import { FILE_OUTCOME_BADGE } from "../lib/badges"
import { SourceDatabasePanel } from "./SourceDatabasePanel"
import { RecordActions } from "./RecordActions"

/**
 * The record behind a line (03 section 3.6): the phone, record type, record id and report with its SHA-256; the
 * record's state; every field in capture order with every value and nested records to any depth; every time with
 * the report's own text beside it; linked files with their check result and the sentence for each kind of absence;
 * the source-row statement; corrections with the original kept beside the corrected value. Non-modal: it sits in
 * the docked slot, so j/k keep moving the list and the panel follows the focused row (UX-4).
 */

const LEVEL_WORDS: Record<string, string> = {
  reviewed: "Interpreted",
  applied_unconfirmed: "Mapped by the system, not yet confirmed",
  generic: "Read generically",
  captured_only: "Held, not yet read",
}

/** A masked sensitive value with its Reveal button; revealing is logged by the server before the value is sent. */
function MaskedValue({ caseId, recordUid, field, index, masked }: { caseId?: string; recordUid: string; field: string; index: number; masked: string }) {
  const [value, setValue] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (value !== null)
    return (
      <span>
        <span className="whitespace-pre-wrap">{value}</span>{" "}
        <span className="text-xs text-muted-foreground">(revealed; your reveal is recorded)</span>
      </span>
    )
  return (
    <span>
      <span aria-label="Hidden sensitive value">{masked}</span>{" "}
      {caseId && (
        <Button
          size="sm"
          variant="outline"
          className="h-6 px-2 text-xs"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            setError(null)
            revealValue(caseId, recordUid, field, index)
              .then((r) => setValue(r.value))
              .catch((e) => setError(failureText(e, "The value could not be revealed.")))
              .finally(() => setBusy(false))
          }}
        >
          Reveal
        </Button>
      )}
      <span className="block text-xs text-muted-foreground">Sensitive. Revealing it records your name and the time.</span>
      {error && (
        <span role="alert" className="block text-xs">
          {error}
        </span>
      )}
    </span>
  )
}

function FieldList({ fields, depth = 0, recordUid, caseId }: { fields: RecordFieldData[]; depth?: number; recordUid: string; caseId?: string }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1" style={{ marginLeft: depth ? 12 : 0 }}>
      {fields.map((f, k) => (
        <div key={`${f.name}-${k}`} className="contents">
          <dt className="text-muted-foreground" title={`${f.kind}${f.data_type ? `, ${f.data_type}` : ""}`}>
            {f.name ?? "(unnamed field)"}
          </dt>
          <dd className="min-w-0 break-words">
            {f.values.length === 0 && f.children.length === 0 && <span className="text-muted-foreground">(no value)</span>}
            {f.values.map((v) => (
              <div key={v.index} data-value>
                {v.empty ? (
                  <span className="text-muted-foreground">(empty)</span>
                ) : v.time ? (
                  <span>
                    {v.time.full} <span className="text-xs text-muted-foreground">(in the report: {v.time.original_text})</span>
                  </span>
                ) : v.masked && f.name ? (
                  <MaskedValue caseId={caseId} recordUid={recordUid} field={f.name} index={v.index} masked={v.text ?? ""} />
                ) : (
                  <span className="whitespace-pre-wrap">{v.text}</span>
                )}
              </div>
            ))}
            {f.children.map((c) => (
              <details key={c.record_uid} className="mt-1 rounded border p-1" open={depth < 1}>
                <summary className="cursor-pointer text-xs">
                  {c.model_type}
                  {c.deleted_state && c.deleted_state !== "Intact" ? ` · ${c.deleted_state}` : ""}
                </summary>
                <FieldList fields={c.fields} depth={depth + 1} recordUid={c.record_uid} caseId={caseId} />
              </details>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function RecordDetailView({
  detail,
  caseId,
  onShowInConversations,
}: {
  detail: RecordDetail
  caseId?: string
  onShowInConversations?: () => void
}) {
  const d = detail
  const readings = d.readings ?? []
  const navigate = useNavigate()
  return (
    <div className="flex flex-col gap-3 text-sm" data-record={d.record_uid}>
      <section aria-label="Record">
        <p className="font-medium">
          {d.extraction.label} · {d.model_type}
        </p>
        <p className="text-xs text-muted-foreground">Record id {d.cellebrite_id ?? "not recorded"}</p>
        <p className="break-all text-xs text-muted-foreground">
          Report {d.extraction.report_filename ?? "not recorded"}
          {d.extraction.report_sha256 ? `, SHA-256 ${d.extraction.report_sha256}` : ""}
        </p>
        {(d.extraction.producer || d.extraction.report_version) && (
          <p className="text-xs text-muted-foreground" data-testid="record-producer">
            Made by {d.extraction.producer ?? "a tool the report does not name"}
            {d.extraction.report_version ? `, report version ${d.extraction.report_version}` : ""}
            {d.extraction.extraction_type ? `, ${d.extraction.extraction_type} extraction` : ""}
          </p>
        )}
      </section>
      {d.parents && d.parents.length > 0 && (
        <section aria-label="Inside" className="text-xs">
          <h3 className="font-semibold">Inside</h3>
          <ol>
            {d.parents.map((p) => (
              <li key={p.record_uid}>
                {caseId ? (
                  <button type="button" className="underline" onClick={() => navigate(`/cases/${caseId}/records/${p.record_uid}`)}>
                    {p.model_type ?? "Record"}{p.title ? `: ${p.title}` : ""}
                  </button>
                ) : (
                  <span>{p.model_type ?? "Record"}{p.title ? `: ${p.title}` : ""}</span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
      {d.attributes && Object.keys(d.attributes).length > 0 && (
        <details className="text-xs" data-testid="record-attributes">
          <summary>Everything the report says about this record</summary>
          <dl className="grid grid-cols-[auto_1fr] gap-x-2">
            {Object.entries(d.attributes).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="break-all">{String(v)}</dd></div>
            ))}
          </dl>
        </details>
      )}
      <section aria-label="State" className="flex flex-wrap gap-2 text-xs">
        {d.state.deleted_state && <span className="rounded bg-muted px-1.5 py-0.5">Deletion state: {d.state.deleted_state}</span>}
        {d.state.is_carved && <span className="rounded bg-muted px-1.5 py-0.5">Recovered by carving</span>}
        {d.state.decoding_confidence && <span className="rounded bg-muted px-1.5 py-0.5">Decoding confidence: {d.state.decoding_confidence}</span>}
        {d.state.source_index && <span className="rounded bg-muted px-1.5 py-0.5">Source index {d.state.source_index}</span>}
        {d.interpretation_level && <span className="rounded bg-muted px-1.5 py-0.5">{LEVEL_WORDS[d.interpretation_level] ?? d.interpretation_level}</span>}
      </section>
      {caseId && readings.length > 0 && (
        <section aria-label="Readings to check" className="rounded border p-2 text-xs">
          <p className="font-medium">{LEVEL_WORDS.applied_unconfirmed}</p>
          {readings.map((r) => {
            const href = `/cases/${caseId}/phone-review?reading=${encodeURIComponent(r.id)}`
            return (
              <div key={r.id} className="mt-1 flex flex-col gap-1">
                <p>{r.sentence}</p>
                <p className="text-muted-foreground">Either choice opens this reading on Needs a decision with its examples, where it is decided.</p>
                <div className="flex gap-2">
                  {/* Both open the reading on Needs a decision with its examples; nothing is decided from here. */}
                  <Button size="sm" variant="outline" onClick={() => navigate(href)}>
                    Looks right
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => navigate(`${href}&answer=not-right`)}>
                    Not right
                  </Button>
                </div>
              </div>
            )
          })}
        </section>
      )}
      {d.corrections.length > 0 && (
        <section aria-label="Corrections" className="rounded border p-2">
          <h3 className="text-xs font-semibold">Corrections</h3>
          {d.corrections.map((c, k) => (
            <p key={k}>
              {c.field_path}: <strong>{c.corrected}</strong> (original: <span className="line-through">{c.original}</span>)
              {c.by ? `. Corrected by ${c.by}` : ""}
              {c.reason ? `: ${c.reason}` : ""}
              {c.current ? "" : " (replaced by a later correction)"}
            </p>
          ))}
        </section>
      )}
      <section aria-label="Fields">
        <FieldList fields={d.fields} recordUid={d.record_uid} caseId={caseId} />
      </section>
      {d.times.length > 0 && (
        <section aria-label="Times" className="text-xs">
          <h3 className="font-semibold">Times</h3>
          {d.times.map((t, k) => (
            <p key={k}>
              {t.field_path}: {t.full} <span className="text-muted-foreground">(in the report: {t.original_text})</span>
            </p>
          ))}
        </section>
      )}
      <section aria-label="Files" className="text-xs">
        <h3 className="font-semibold">Files</h3>
        {d.files_absence && <p>{d.files_absence}</p>}
        {d.files.map((f, k) => (
          <div key={k} className="rounded border p-1">
            <p className="break-all">{f.path ?? f.reference ?? "(no path in the report)"}</p>
            {f.original_path && <p className="break-all text-muted-foreground">On the phone at {f.original_path}</p>}
            {f.hashes && (f.hashes.stated_md5 || f.hashes.stated_sha256 || f.hashes.computed_sha256) && (
              <p className="break-all text-muted-foreground" data-testid="file-hashes">
                {f.hashes.stated_md5 ? `MD5 in the report ${f.hashes.stated_md5}. ` : ""}
                {f.hashes.stated_sha256 ? `SHA-256 in the report ${f.hashes.stated_sha256}. ` : ""}
                {f.hashes.computed_sha256 ? `SHA-256 of the file in the production ${f.hashes.computed_sha256}.` : ""}
              </p>
            )}
            <p className="text-muted-foreground">
              Found by {f.mechanism.replace(/_/g, " ")}
              {f.category ? `, ${f.category}` : ""}
              {f.verification && FILE_OUTCOME_BADGE[f.verification] ? `, ${FILE_OUTCOME_BADGE[f.verification]}` : ""}
            </p>
            {f.absence && <p>{f.absence}</p>}
          </div>
        ))}
      </section>
      <SourceDatabasePanel caseId={caseId} detail={d} />
      {(d.reparse ?? []).length > 0 && (
        <section aria-label="Read again by an independent tool" className="space-y-1 rounded border p-2 text-xs">
          <h3 className="font-semibold">Read again by an independent tool</h3>
          {(d.reparse ?? []).map((r, k) => (
            <div key={k} data-testid="reparse-reading">
              <p className="font-medium">
                {r.read_by ?? "Read by the tool"}{r.reparse?.artefact ? ` (${r.reparse.artefact}, row ${r.reparse.row_index})` : ""}:{" "}
                {r.kind === "present_in_both" ? "the same as the report" : r.kind === "time_differs" ? `a different time, ${r.difference_hours} hours from the report's` : "different content from the report's"}
              </p>
              {r.reparse?.instant && <p>Time: {r.reparse.instant} (as the tool wrote it: {r.reparse.original ?? "not given"})</p>}
              {Object.entries(r.reparse?.shown ?? {}).filter(([, v]) => v !== null && v !== "").map(([k2, v]) => (
                <p key={k2} className="break-all">{k2}: {String(v)}</p>
              ))}
              <p className="text-muted-foreground">This is the tool's reading, shown beside the report's record; it does not change the record.</p>
            </div>
          ))}
        </section>
      )}
      <div className="flex flex-wrap gap-2">
        <CopyButton rows={1} noun="record" label="Copy record as text" build={() => ({ text: d.as_text, html: `<pre>${htmlEscape(d.as_text)}</pre>` })} />
        <CopyButton rows={1} noun="record id" label="Copy record id" build={() => ({ text: d.cellebrite_id ?? d.record_uid })} />
        {onShowInConversations && (
          <Button size="sm" variant="outline" onClick={onShowInConversations}>
            Show in Conversations
          </Button>
        )}
      </div>
      {caseId && <RecordActions detail={d} caseId={caseId} />}
    </div>
  )
}

export function PhoneRecordPanel({
  caseId,
  recordUid,
  zone,
  onClose,
  onShowInConversations,
}: {
  caseId: string
  recordUid: string | null
  zone?: string
  onClose: () => void
  onShowInConversations?: () => void
}) {
  const q = useQuery({
    queryKey: ["phone-record", caseId, recordUid, zone],
    queryFn: () => getRecord(caseId, recordUid as string, zone),
    enabled: !!recordUid,
  })
  return (
    <DockedPanel title="Record behind this message" open={!!recordUid} onClose={onClose}>
      {q.isLoading && <p className="text-sm text-muted-foreground">Loading the record</p>}
      {q.isError && (
        <div role="alert" className="text-sm">
          <p>{failureText(q.error, "The record could not be loaded.")}</p>
          <Button size="sm" variant="outline" onClick={() => void q.refetch()}>
            Try again
          </Button>
        </div>
      )}
      {q.data && <RecordDetailView detail={q.data} caseId={caseId} onShowInConversations={onShowInConversations} />}
    </DockedPanel>
  )
}
