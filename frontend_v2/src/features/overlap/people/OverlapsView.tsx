import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { openCorroborate } from "@/features/leads/open"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"
import { isRefused, memberOf, overlapsAPI, type OverlapKind, type OverlapRecord, type Overlaps, type Pair } from "./api"
import { TONE, squareWords } from "./square"

const LEGEND: [string, string][] = [
  ["strong", "Strong link"],
  ["probable", "Probable"],
  ["possible", "Possible"],
  ["coincidence", "Coincidence likely or explained"],
  ["no_link_found", "No link found, with what was searched"],
  ["not_weighed", "Records found, not weighed yet"],
  ["nothing", "Nothing in the records"],
]

const KIND_ORDER: OverlapKind[] = ["contact", "through_others", "groups", "shared", "place", "access", "money", "documents"]

export function OverlapsView({ caseId }: { caseId: string }) {
  const [fresh, setFresh] = useState(false)
  const q = useQuery({
    queryKey: ["corroborate-overlaps", caseId, fresh],
    queryFn: () => overlapsAPI.get(caseId, fresh),
    staleTime: 60_000,
  })
  const [picked, setPicked] = useState<string | null>(null)
  if (q.isLoading) {
    return (
      <div role="status" className="flex items-center gap-2 px-5 py-6 text-sm text-muted-foreground sm:px-8">
        <LoadingSpinner /> Reading every pair of people in the case…
      </div>
    )
  }
  if (q.isError || !q.data) {
    return <p role="alert" className="px-5 py-6 text-sm sm:px-8">Who overlaps with whom could not be read. Try again in a minute.</p>
  }
  if (isRefused(q.data)) return <p role="status" className="px-5 py-6 text-sm sm:px-8">{q.data.words}</p>
  const data = q.data
  const pair = data.pairs.find((p) => `${p.a}|${p.b}` === picked) ?? null
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-8" data-testid="overlaps-view">
      <div className="mx-auto max-w-6xl">
        <h2 className="font-display text-xl font-semibold">Who overlaps with whom</h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Every pair of people in the case, against every kind of overlap: contact direct or through others, groups,
          shared words and files, places, access logs, money and documents. A square shows the pair's level from its
          lead; pick one to see why.
        </p>
        <div className="mt-4 flex flex-col gap-6 xl:flex-row">
          <div className="min-w-0 flex-1">
            <Grid data={data} picked={picked} onPick={setPicked} />
            <Legend />
            <WorthALook data={data} onPick={setPicked} />
            <Notes data={data} onRefresh={() => setFresh(true)} />
          </div>
          <div className="xl:w-[26rem] xl:shrink-0">
            {pair ? <PairDetail caseId={caseId} data={data} pair={pair} /> : (
              <p className="rounded border border-dashed p-4 text-sm text-muted-foreground">
                Pick a square to see each kind of overlap for that pair, with its records.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Grid({ data, picked, onPick }: { data: Overlaps; picked: string | null; onPick: (k: string) => void }) {
  const people = data.people
  const byKey = new Map(data.pairs.map((p) => [`${p.a}|${p.b}`, p]))
  const find = (a: string, b: string) => byKey.get(`${a}|${b}`) ?? byKey.get(`${b}|${a}`)
  return (
    <div className="overflow-x-auto" role="region" aria-label="Pairs of people">
      <table className="border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th />
            {people.slice(1).map((p) => (
              <th key={p.key} scope="col" className="min-w-24 px-1 text-left font-medium" title={p.full_label}>{p.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {people.slice(0, -1).map((row, i) => (
            <tr key={row.key}>
              <th scope="row" className="whitespace-nowrap pr-2 text-left font-medium" title={row.full_label}>{row.label}</th>
              {people.slice(1).map((col, j) => {
                if (j < i) return <td key={col.key} />
                const p = find(row.key, col.key)
                if (!p) return <td key={col.key} />
                const w = squareWords(p)
                const k = `${p.a}|${p.b}`
                return (
                  <td key={col.key}>
                    <button
                      type="button"
                      aria-pressed={picked === k}
                      aria-label={`${p.label}: ${w.title}${w.sub ? `, ${w.sub}` : ""}`}
                      onClick={() => onPick(k)}
                      className={cn("flex min-h-12 w-full flex-col items-start rounded border px-2 py-1 text-left", w.tone,
                        picked === k && "ring-2 ring-brand-500")}
                    >
                      <span className="font-semibold leading-tight">{w.title}</span>
                      {w.sub && <span className="text-[10px] leading-tight opacity-80">{w.sub}</span>}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {data.left_out.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          {data.left_out.length} more {data.left_out.length === 1 ? "person has" : "people have"} fewer records and
          {data.left_out.length === 1 ? " is" : " are"} not in the grid: {data.left_out.join(", ")}.
        </p>
      )}
    </div>
  )
}

function Legend() {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="What the squares mean">
      {LEGEND.map(([k, words]) => (
        <li key={k} className="flex items-center gap-1">
          <span className={cn("inline-block size-3 rounded-sm border", TONE[k])} aria-hidden /> {words}
        </li>
      ))}
    </ul>
  )
}

function WorthALook({ data, onPick }: { data: Overlaps; onPick: (k: string) => void }) {
  if (!data.worth_a_look.length) return null
  return (
    <section className="mt-5 rounded border border-amber-500/40 bg-amber-400/5 p-3" aria-label="Worth a look">
      <h3 className="text-sm font-semibold">Worth a look</h3>
      <p className="text-xs text-muted-foreground">Pairs who never contact each other directly, linked another way.</p>
      <ul className="mt-2 flex flex-col gap-2 text-sm">
        {data.worth_a_look.map((w) => (
          <li key={`${w.a}|${w.b}`}>
            <button type="button" className="text-left hover:underline" onClick={() => onPick(`${w.a}|${w.b}`)}>
              {w.words.join(" ")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Notes({ data, onRefresh }: { data: Overlaps; onRefresh: () => void }) {
  return (
    <div className="mt-4 text-xs text-muted-foreground">
      <ul className="list-disc pl-4">
        {data.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
      {data.read_at && (
        <p className="mt-1">
          Read {new Date(data.read_at).toLocaleString("en-GB")}.{" "}
          <button type="button" className="underline" onClick={onRefresh}>Read again</button>
        </p>
      )}
    </div>
  )
}

function when(r: OverlapRecord) {
  if (!r.at) return "no date"
  const d = new Date(r.at)
  return r.day_only ? d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
    : d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

function money(minor: number | null) {
  return minor == null ? "" : `$${(Math.abs(minor) / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`
}

function words(x: unknown): string[] {
  if (!x) return []
  if (Array.isArray(x)) return x.map((v) => (typeof v === "string" ? v : String((v as { words?: string; text?: string }).words ?? (v as { text?: string }).text ?? ""))).filter(Boolean)
  return typeof x === "string" ? [x] : []
}

export function PairDetail({ caseId, data, pair }: { caseId: string; data: Overlaps; pair: Pair }) {
  const names = new Map(data.people.map((p) => [p.key, p]))
  const a = names.get(pair.a)!
  const b = names.get(pair.b)!
  const lead = pair.leads?.[0]
  const notFound = KIND_ORDER.filter((k) => !pair.kinds[k]?.count)
  const kindName = new Map(data.kinds.map((k) => [k.key, k]))
  const lowers = words(lead?.lowers)
  return (
    <section aria-label={`${pair.label}: every kind of overlap`} className="rounded border p-4" data-testid="pair-detail">
      <h3 className="text-base font-semibold">{a.label} and {b.label}</h3>
      <p className="mt-1 text-sm">
        {pair.level ? <><b>{pair.level.name}</b>{pair.level.sentence ? ` · ${pair.level.sentence}` : ""}</> :
          pair.state === "nothing" ? "Nothing in the records links them." :
            "Not weighed yet: Corroborate this pair to weigh it against ordinary days and save it to Leads."}
      </p>
      {lead && <p className="text-xs text-muted-foreground">Level from the lead “{lead.title ?? "untitled"}”, set by Loupe's rules.</p>}
      <dl className="mt-3 flex flex-col gap-3 text-sm">
        {KIND_ORDER.filter((k) => pair.kinds[k]?.count).map((k) => {
          const r = pair.kinds[k]
          return (
            <div key={k}>
              <dt className="font-semibold">{kindName.get(k)?.name ?? k}</dt>
              <dd>
                {r.words}
                {k === "documents" && (
                  <ul className="mt-1 text-xs">
                    {(r.documents ?? []).slice(0, 8).map((d) => (
                      <li key={d.file_id}>
                        {d.file}: {Object.entries(d.pages).map(([who, pages]) =>
                          `${names.get(who)?.label ?? who} ${d.by[who] === "model" ? `read by a model${pages.length ? `, page ${pages.join(", ")}` : ""}` : "by full name in the text"}`).join("; ")}
                      </li>
                    ))}
                  </ul>
                )}
                {(k === "contact" || k === "money") && (r.records ?? []).length > 0 && (
                  <ul className="mt-1 flex flex-col gap-0.5 text-xs text-muted-foreground">
                    {(r.records ?? []).slice(0, 5).map((x) => (
                      <li key={x.ref}>
                        {when(x)}{x.from ? `, ${x.from}` : ""}: {x.body ? `“${x.body}”` : x.kind}{x.amount_minor != null ? ` ${money(x.amount_minor)}` : ""}
                        {x.copies > 1 ? " (on both phones)" : ""}{x.deleted ? " (deleted on one phone)" : ""}
                      </li>
                    ))}
                    {(r.records ?? []).length > 5 && <li>{r.count - 5} more</li>}
                  </ul>
                )}
              </dd>
            </div>
          )
        })}
        {lowers.length > 0 && (
          <div>
            <dt className="font-semibold">Lowers it</dt>
            <dd>{lowers.join(" ")}</dd>
          </div>
        )}
        {notFound.length > 0 && (
          <div>
            <dt className="font-semibold">Not found</dt>
            <dd>
              <ul className="text-xs">
                {notFound.map((k) => (
                  <li key={k}><span className="font-medium">{kindName.get(k)?.name}</span>: {pair.kinds[k]?.searched === false ? "not searched in this release." : `searched ${kindName.get(k)?.searched}.`}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="primary"
          onClick={() => openCorroborate({
            caseId,
            screen: "who overlaps with whom",
            label: `${a.label} and ${b.label}`,
            members: [memberOf(a), memberOf(b)],
            people: [a.key, b.key],
          })}
        >
          Corroborate this pair
        </Button>
      </div>
    </section>
  )
}
