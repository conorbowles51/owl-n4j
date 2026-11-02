import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { getFindingExplanation } from "@/features/phones/api"

const n = (v: number) => v.toLocaleString("en-US")
const plural = (v: number, one: string, many: string) => `${n(v)} ${v === 1 ? one : many}`

/**
 * How this was found (07 J-17): shown under every finding that holds phone links. Nothing in it is typed: the
 * scope and searches, the readings by confirmation state, the identity decisions, the assumptions and the label
 * all come from the finding's links and the case's records.
 */
export function HowThisWasFound({ caseId, entryId }: { caseId: string; entryId: string }) {
  const q = useQuery({
    queryKey: ["finding-explanation", caseId, entryId],
    queryFn: ({ signal }) => getFindingExplanation(caseId, entryId, signal),
    staleTime: 30_000,
    retry: false,
  })
  const x = q.data
  if (q.isError) return <p className="px-4 pb-3 text-xs" role="alert">How this was found could not be loaded.</p>
  if (!x || !x.has_phone_links) return null
  const r = x.readings
  return (
    <section aria-label={`${x.heading}: ${entryId}`} className="mx-4 mb-3 rounded-md border border-border bg-muted/20 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold">{x.heading}</h3>
        {x.label && <Badge variant={x.label === "Result for report" ? "outline" : "warning"}>{x.label}</Badge>}
        <span className="text-muted-foreground">from {plural(x.links.total, "phone link", "phone links")}</span>
      </div>
      {x.label_reasons && x.label_reasons.length > 0 && (
        <ul className="mt-1 list-disc pl-4">
          {x.label_reasons.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      )}
      {x.scope && x.scope.length > 0 && (
        <div className="mt-1">
          <span className="font-medium">Saved scope: </span>
          {x.scope
            .map((s) => `${s.words}${typeof s.records === "number" ? ` (${plural(s.records, "record", "records")})` : ""}${s.missing ? " (no longer in the current reading)" : ""}`)
            .join("; ")}
        </div>
      )}
      {x.searches && x.searches.length > 0 && (
        <div>
          <span className="font-medium">Searches: </span>
          {x.searches.map((s) => `“${s.query}”${s.exact ? " (exact characters)" : ""}`).join(", ")}
        </div>
      )}
      {r && (
        <div>
          <span className="font-medium">Readings: </span>
          {plural(r.records, "record", "records")}: {n(r.confirmed)} confirmed by a person, {n(r.unconfirmed)} mapped by the system and not yet confirmed, {n(r.as_recorded)} read as recorded
          {r.not_in_current_reading ? `, ${n(r.not_in_current_reading)} no longer in the current reading` : ""}.
        </div>
      )}
      {x.identities && x.identities.length > 0 && (
        <div>
          <span className="font-medium">Identity decisions: </span>
          {x.identities.map((i) => `${i.identity}: ${i.decisions ? plural(i.decisions, "decision", "decisions") + " by a person" : "no decision by a person"}${i.linked_to_person ? ", linked to a person" : ""}`).join("; ")}
        </div>
      )}
      {x.assumptions && x.assumptions.length > 0 && (
        <div>
          <span className="font-medium">Assumptions: </span>
          <ul className="list-disc pl-4">
            {x.assumptions.map((a) => (
              <li key={`${a.phone}:${a.code}`}>
                {a.words} <span className="text-muted-foreground">({a.code})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
