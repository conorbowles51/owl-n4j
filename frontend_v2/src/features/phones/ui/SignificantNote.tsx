import { useQuery } from "@tanstack/react-query"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"
import { getSignificantSummary } from "../api"
import { fmt } from "./count-sentence"

/**
 * The Significant layer on a phone screen (07 XF-11, 7.3): a toggle, never a silent narrowing. With the layer on the
 * screen still shows all records and says how many phone identities are significant; "Show only those" narrows it,
 * and the narrowed screen says what is hidden and how to get it back. `hiddenWords` is the screen's own true count.
 */
export function SignificantNote({ caseId, on, onChange, hiddenWords }: { caseId: string; on: boolean; onChange: (on: boolean) => void; hiddenWords?: string | null }) {
  const layer = useCaseLayer(caseId)
  const q = useQuery({ queryKey: ["phone-significant", caseId], queryFn: () => getSignificantSummary(caseId), enabled: !!caseId && (layer === "significant" || on), staleTime: 30_000 })
  if ((layer !== "significant" && !on) || !q.data) return null
  const { significant, total, words } = q.data
  if (on)
    return (
      <p role="status" className="text-sm" data-testid="significant-note">
        Showing only records with the {fmt(significant)} significant {significant === 1 ? "phone identity" : "phone identities"} of {fmt(total)}.
        {hiddenWords ? ` ${hiddenWords}` : " The other records are hidden."}{" "}
        <button type="button" className="underline underline-offset-2" onClick={() => onChange(false)}>
          Show all records
        </button>
      </p>
    )
  return (
    <p role="status" className="text-sm" data-testid="significant-note">
      {words}{" "}
      {significant > 0 && (
        <button type="button" className="underline underline-offset-2" onClick={() => onChange(true)}>
          Show only those
        </button>
      )}
    </p>
  )
}
