import { formatFull, zoneName } from "@/lib/evidence-time"
import type { RecordDetail } from "../schemas"

/** The lines of the original-value popover (03 section 3.2). */

export interface TimeCellProps {
  caseId: string
  recordUid: string
  time: { instant: string | null; row: string; full: string; offset_present: boolean; time_field?: string | null }
  zone: string
  zoneBasis?: string
  modelType?: string
}

export function originalLines(detail: RecordDetail | null, props: TimeCellProps): { label: string; value: string }[] {
  const t =
    detail?.times.find((x) => x.record_uid === props.recordUid && (!props.time.time_field || x.field_path === props.time.time_field)) ??
    detail?.times.find((x) => x.record_uid === props.recordUid)
  const shown = props.time.instant ? formatFull(props.time.instant, props.zone) : props.time.full
  const lines = [{ label: "Shown as", value: shown }]
  if (!t) {
    lines.push({ label: "In the report", value: detail ? "This record has no time value." : "Loading" })
    return lines
  }
  lines.push({ label: "In the report", value: t.original_text })
  lines.push({
    label: "Offset stored",
    value: t.offset_present ? offsetWords(t.original_text) : "No offset in the report. Loupe has not assumed one.",
  })
  lines.push({ label: "Field", value: `${t.field_path} on ${detail?.model_type ?? props.modelType ?? "this record"}` })
  lines.push({ label: "Zone used", value: `${zoneName(props.zone)}, ${props.zone}${props.zoneBasis ? `: ${zoneBasisWords(props.zoneBasis)}` : ""}` })
  return lines
}

function offsetWords(original: string): string {
  const m = original.match(/(Z|[+-]\d{2}:?\d{2})$/)
  if (!m) return "No offset in the report. Loupe has not assumed one."
  const off = m[1] === "Z" ? "+00:00" : m[1]
  return off === "+00:00" ? "+00:00 (the report converted this time to UTC)" : off
}

export function zoneBasisWords(basis: string): string {
  switch (basis) {
    case "device_metadata":
      return "the phone's time zone as stated in the report"
    case "decision":
      return "set by a person"
    case "case_setting":
      return "the case time zone"
    case "phones_device_zone":
      return "every phone in the case states this zone"
    case "chosen_utc":
      return "chosen"
    default:
      return "no phone time zone is stated, so UTC is used"
  }
}
