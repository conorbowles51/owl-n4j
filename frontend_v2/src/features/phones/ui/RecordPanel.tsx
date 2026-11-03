import { Button } from "@/components/ui/button"
import { CopyButton } from "@/components/ui/copy-button"
import { htmlEscape } from "@/lib/copy-text"
import { participantsLine, type PhoneRecordView } from "../types"
import { instantWords } from "../lib/time-words"
import { BadgeRow, OriginMark } from "./OriginMark"
import { PhoneChip } from "./PhoneChip"
import { recordCopyText, usedInWords } from "./record-words"

export function RecordPanelContent({
  record,
  onAddTo,
  onAround,
  onWindow,
  onCorrect,
  canCorrect = true,
  correctDisabledReason,
}: {
  record: PhoneRecordView
  onAddTo?: () => void
  onAround?: () => void
  onWindow?: () => void
  onCorrect?: () => void
  canCorrect?: boolean
  correctDisabledReason?: string
}) {
  const r = record
  const text = recordCopyText(r)
  return (
    <div className="flex flex-col gap-3 text-sm" data-record={r.id}>
      <div className="flex flex-wrap items-center gap-2">
        <PhoneChip label={r.phone.label} index={r.phone.index} extractionDate={r.phone.extractionDate} />
        <span>
          {r.typeWords}
          {r.app ? ` · ${r.app}` : ""}
        </span>
        <BadgeRow badges={r.badges} />
      </div>
      <p className="font-medium">{r.time ? instantWords(r.time, r.zone, true) : "No time recorded. Listed at the end."}</p>
      {(r.from || r.to) && (
        <p>
          <span className="sr-only">From and to: </span>
          {participantsLine(r)}
        </p>
      )}
      {r.body !== undefined && (
        <p className="whitespace-pre-wrap break-words rounded border bg-background p-2">{r.body === null || r.body === "" ? <em>No text in this message</em> : r.body}</p>
      )}
      {r.fields && r.fields.length > 0 && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
          {r.fields.map((f) => (
            <div key={f.label} className="contents">
              <dt className="text-muted-foreground">{f.label}</dt>
              <dd className="break-words">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <OriginMark origin={r.origin} />
      <div className="flex flex-wrap gap-2">
        {onAddTo && (
          <Button size="sm" onClick={onAddTo}>
            Add to…
          </Button>
        )}
        {onAround && (
          <Button size="sm" variant="outline" onClick={onAround}>
            Around this time
          </Button>
        )}
        {onWindow && (
          <Button size="sm" variant="outline" onClick={onWindow}>
            Open the window around this
          </Button>
        )}
        {onCorrect && (
          <Button size="sm" variant="outline" onClick={onCorrect} disabled={!canCorrect} title={canCorrect ? undefined : correctDisabledReason}>
            Correct this value
          </Button>
        )}
        <CopyButton rows={1} noun="record" build={() => ({ text, html: `<pre>${htmlEscape(text)}</pre>` })} />
      </div>
      {!canCorrect && correctDisabledReason && <p className="text-muted-foreground">{correctDisabledReason}</p>}
      <section aria-label="Used in this case" className="rounded border p-2">
        <h3 className="text-xs font-semibold">Used in this case</h3>
        <p>{usedInWords(r.usedIn)}</p>
      </section>
      <p className="text-xs text-muted-foreground">Record {r.id}</p>
    </div>
  )
}
