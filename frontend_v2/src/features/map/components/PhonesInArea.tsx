import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { getPhoneMapArea } from "@/features/phones/api"
import type { BoundingShape } from "../stores/map.store"
import { PLACE_LABEL } from "../lib/place-label"
import { areaConversationsHref } from "../lib/area-links"

const n = (v: number) => v.toLocaleString("en-US")

/**
 * Drawing an area on the Map lists "Phones seen in this area" (03 13.3, 07 J-10): each phone with a position inside
 * it, the exact count, the first and last time there, and its conversations over that time. Nothing is capped.
 */
export function PhonesInArea({ caseId, shape }: { caseId: string; shape: BoundingShape }) {
  const ring = shape.coordinates.map(([lng, lat]) => [lng, lat])
  const q = useQuery({
    queryKey: ["phone-map-area", caseId, shape.id, ring.map((c) => c.join(",")).join(";")],
    queryFn: ({ signal }) => getPhoneMapArea(caseId, ring, {}, signal),
  })
  return (
    <section aria-label="Phones seen in this area" className="absolute right-14 top-14 z-10 flex max-h-[50%] w-80 flex-col gap-1 overflow-auto rounded-lg border border-border bg-card/95 p-3 text-xs shadow-md backdrop-blur">
      <h2 className="text-sm font-semibold">Phones seen in this area</h2>
      {q.isLoading && <p>Counting the positions inside the area…</p>}
      {q.isError && <p role="alert">The area could not be read: {q.error instanceof Error ? q.error.message : "try again"}.</p>}
      {q.data && (
        <>
          <p role="status">
            {q.data.phones_total === 0 ? "No phone has a position inside this area." :
              `${n(q.data.phones_total)} ${q.data.phones_total === 1 ? "phone" : "phones"}, ${n(q.data.points_total)} positions inside the area.`}
            {q.data.points_without_time > 0 ? ` ${n(q.data.points_without_time)} of them have no time.` : ""}
          </p>
          <ul className="flex flex-col gap-1">
            {q.data.phones.map((p) => (
              <li key={p.extraction_id} className="rounded border border-border/60 px-2 py-1">
                <div className="font-medium">{p.phone_label}: {n(p.points)} {p.points === 1 ? "position" : "positions"}</div>
                {p.first && <div>{p.first.slice(0, 16).replace("T", " ")} to {p.last?.slice(0, 16).replace("T", " ")} UTC</div>}
                <Link className="underline" to={areaConversationsHref(caseId, p.extraction_id, p.first, p.last)}>
                  Conversations on this phone at that time
                </Link>
              </li>
            ))}
          </ul>
          <p className="font-medium">{PLACE_LABEL}.</p>
        </>
      )}
    </section>
  )
}
