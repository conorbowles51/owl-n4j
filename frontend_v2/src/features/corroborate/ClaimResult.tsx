import type { Corroboration } from "./result-types"
import { LearnMore } from "@/components/ui/learn-more"

const LEVEL_CLASS: Record<string, string> = { claim_fits: "border-green-700", claim_contradicts: "border-red-700", cant_tell: "border-slate-400" }
const WORDS: Record<string, string> = { fits: "Fits", contradicts: "Contradicts", cant_tell: "Can't tell" }

/** The result of a confirmed free-text claim (lx-corrostatement D): fits, contradicts or Can't tell, the records behind it and what was searched. */
export function ClaimResult({ c }: { c: Corroboration }) {
  const s = c.searched as unknown as { records_read?: Record<string, number>; window?: { label?: string; zone?: string; start: string; end: string } } | undefined
  const read = Object.entries(s?.records_read ?? {})
  return (
    <div className="space-y-4" data-testid="claim-result">
      <section aria-label="Level" className={`rounded border-l-4 p-3 ${LEVEL_CLASS[c.level.key] ?? ""}`}>
        <p className="text-sm text-muted-foreground">“{c.claim?.sentence}”</p>
        <h2 className="text-lg font-semibold">{WORDS[(c.level as { verdict?: string }).verdict ?? ""] ?? c.level.name}</h2>
        <p>{c.level.sentence}</p>
        <p className="text-xs text-muted-foreground">Set by a stated rule from the phones' records, not by a model. Confirmed by {c.claim?.confirmed_by ?? "a person"}{c.claim?.edited.length ? `; changed from Loupe's reading: ${c.claim.edited.join(", ")}` : ""}.<LearnMore term="Fits and Contradicts" /></p>
      </section>
      <section aria-label="What the records show">
        <h2 className="font-semibold">What the records show</h2>
        <ul className="list-disc pl-5 text-sm">{c.level.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        {(c.cited?.length ?? 0) > 0 && (
          <ul className="pt-1 text-xs text-muted-foreground">
            {c.cited!.map((r) => <li key={r.ref}>{r.ref}{r.person ? ` · ${r.person}` : ""} · {r.at.slice(0, 16).replace("T", " ")} UTC{r.inside === undefined ? "" : r.inside ? " · inside the place" : " · outside the place"}</li>)}
          </ul>
        )}
      </section>
      <section aria-label="What was searched">
        <h2 className="font-semibold">What was searched</h2>
        <p className="text-sm">{s?.window?.label ?? "No window"}. {read.length ? read.map(([k, n]) => `${n.toLocaleString("en-US")} ${k}${n === 1 ? "" : "s"}`).join(", ") + " read." : "No records were read."}</p>
        {c.gaps.length > 0 && <ul className="list-disc pl-5 text-sm">{c.gaps.map((g, i) => <li key={i}>{g.words}</li>)}</ul>}
      </section>
    </div>
  )
}
