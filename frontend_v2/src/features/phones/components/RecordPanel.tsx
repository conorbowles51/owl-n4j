import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { CopyButton } from "@/components/ui/copy-button"
import { htmlEscape } from "@/lib/copy-text"
import { failureText, getRecord } from "../api"
import type { RecordDetail, RecordFieldData } from "../schemas"
import { DockedPanel } from "../ui/DockedPanel"
import { FILE_OUTCOME_BADGE } from "../lib/badges"

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

function FieldList({ fields, depth = 0 }: { fields: RecordFieldData[]; depth?: number }) {
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
                <FieldList fields={c.fields} depth={depth + 1} />
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
      </section>
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
        <FieldList fields={d.fields} />
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
            <p className="text-muted-foreground">
              Found by {f.mechanism.replace(/_/g, " ")}
              {f.category ? `, ${f.category}` : ""}
              {f.verification && FILE_OUTCOME_BADGE[f.verification] ? `, ${FILE_OUTCOME_BADGE[f.verification]}` : ""}
            </p>
            {f.absence && <p>{f.absence}</p>}
          </div>
        ))}
      </section>
      <p className="text-xs">{d.source_row.available ? "Open source row" : d.source_row.reason}</p>
      <div className="flex flex-wrap gap-2">
        <CopyButton rows={1} noun="record" label="Copy record as text" build={() => ({ text: d.as_text, html: `<pre>${htmlEscape(d.as_text)}</pre>` })} />
        <CopyButton rows={1} noun="record id" label="Copy record id" build={() => ({ text: d.cellebrite_id ?? d.record_uid })} />
        {onShowInConversations && (
          <Button size="sm" variant="outline" onClick={onShowInConversations}>
            Show in Conversations
          </Button>
        )}
      </div>
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
