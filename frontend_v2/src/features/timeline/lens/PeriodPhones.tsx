import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Lanes, type LaneRow } from "@/features/pattern/components/Lanes"
import { getPeriodCrossing } from "@/features/phones/api"
import { lensBuckets, lensIndex, type LensFilter } from "./lens-api"
import { LensList } from "./PhoneLens"

const n = (x: number) => x.toLocaleString("en-US")
const DAY = /^\d{4}-\d{2}-\d{2}$/

/**
 * XF-4 (07 section 7.2): from a Timeline period to what the phones did in it. One lane per phone, counted from the
 * lens for messages, calls and emails, with the hours a phone recorded nothing drawn as "No data"; each phone's count
 * is the Conversations count for its link (the server checks both against the same filter). Choosing a mark lists
 * exactly that hour, day or week of that phone below the lanes, as the phone lens does, so the list holds the number
 * the mark shows (a Conversations link can only narrow by whole days).
 */
export function PeriodPhones({ caseId, caseName, from, to }: { caseId: string; caseName: string; from: string | null; to: string | null }) {
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState<{ phone: string; label: string; start: string; end: string } | null>(null)
  const valid = !!from && !!to && DAY.test(from.slice(0, 10)) && DAY.test(to.slice(0, 10))
  const f = valid ? from!.slice(0, 10) : ""
  const t = valid ? to!.slice(0, 10) : ""
  const period = useQuery({
    queryKey: ["timeline-period-phones", caseId, f, t],
    queryFn: () => getPeriodCrossing(caseId, f, t),
    enabled: open && valid,
  })
  const filter = period.data?.lens_filter as LensFilter | undefined
  const idx = useQuery({
    queryKey: ["timeline-period-lens", filter],
    queryFn: () => lensIndex(filter!),
    enabled: !!filter,
  })
  const spanDays = valid ? (Date.parse(`${t}T00:00:00Z`) - Date.parse(`${f}T00:00:00Z`)) / 86400000 + 1 : 0
  const bucket = spanDays <= 2 ? "hour" : spanDays <= 3700 ? "day" : "week"
  const buckets = useQuery({
    queryKey: ["timeline-period-buckets", filter, idx.data?.snapshot, bucket],
    queryFn: () => lensBuckets(filter!, idx.data!.snapshot, filter!.from_instant as string, filter!.to_instant as string, bucket),
    enabled: !!filter && !!idx.data,
  })
  const pickedFilter = useMemo<LensFilter | null>(
    () => (picked && filter ? { ...filter, phones: [picked.phone], from_instant: picked.start, to_instant: new Date(new Date(picked.end).getTime() - 1).toISOString(), include_no_time: false } : null),
    [picked, filter],
  )
  if (!valid) return null
  const step = bucket === "hour" ? 3600000 : bucket === "day" ? 86400000 : 7 * 86400000
  const counts = new Map((period.data?.phones ?? []).map((p) => [p.extraction_id, p]))
  const rows: LaneRow[] = (buckets.data?.lanes ?? []).map((l) => ({
    id: l.key,
    label: l.label,
    total: l.buckets.reduce((a, b) => a + b.count, 0),
    bands: l.buckets.filter((b) => b.no_data).map((b) => ({ start: b.start, end: new Date(new Date(b.start).getTime() + step).toISOString(), state: "no_data", words: buckets.data!.no_data_words })),
    marks: l.buckets.filter((b) => b.count > 0).map((b) => ({ key: `${l.key}-${b.start}`, at: b.start, label: `${n(b.count)} ${b.count === 1 ? "entry" : "entries"}`, tone: "moderate" as const,
      onClick: () => setPicked({ phone: l.key, label: l.label, start: b.start, end: new Date(new Date(b.start).getTime() + step).toISOString() }) })),
  }))
  return (
    <div className="flex flex-col gap-2 border-b px-4 py-2" aria-label="What the phones did in this period">
      <div className="flex items-center gap-2 text-sm">
        <Button size="sm" variant="outline" aria-expanded={open} onClick={() => setOpen(!open)}>What the phones did</Button>
        <span className="text-xs text-muted-foreground">From {f} to {t}</span>
      </div>
      {open && period.isLoading && <p className="text-sm text-muted-foreground">Counting the phones' messages and calls…</p>}
      {open && period.isError && <p role="alert" className="text-sm">The phones could not be read for this period.</p>}
      {open && period.data && (
        <>
          <p className="text-sm">{period.data.sentence}</p>
          <ul className="flex flex-wrap gap-3 text-sm">
            {period.data.phones.map((p) => (
              <li key={p.extraction_id}>
                <Link className="underline" to={p.conversations_href}>{p.label}: {n(p.count)} in Conversations</Link>
                {p.no_time ? <span className="text-muted-foreground"> and {n(p.no_time)} with no time, not placed in any period</span> : null}
              </li>
            ))}
          </ul>
          {buckets.data && filter && (
            <Lanes start={filter.from_instant as string} end={filter.to_instant as string} zone={buckets.data.zone} rows={rows} />
          )}
          {pickedFilter && picked
            ? <LensList caseId={caseId} caseName={caseName} filter={pickedFilter} filterWords={`${picked.label}; one ${bucket} from the lanes`} />
            : buckets.data && <p className="text-sm text-muted-foreground">Choose a mark in a lane to list its entries here.</p>}
        </>
      )}
    </div>
  )
}
