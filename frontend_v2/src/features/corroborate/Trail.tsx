import { useQuery } from "@tanstack/react-query"
import { InfoTip } from "@/components/ui/info-tip"
import { Link } from "react-router-dom"
import { relationAPI } from "@/features/relations/api"

const MOVED: Record<string, string> = { raised: "Level went up", lowered: "Level went down", unchanged: "Level did not change" }

/** The steps of a build-out. Opening an earlier step shows the result without what the later steps added. */
export function Trail({ caseId, selectionId }: { caseId: string; selectionId: string }) {
  const q = useQuery({ queryKey: ["relation-trail", caseId, selectionId], queryFn: () => relationAPI.trail(caseId, selectionId) })
  if (!q.data || q.data.steps.length < 2) return null
  return (
    <section aria-label="Trail" data-testid="corroborate-trail">
      <h2 className="font-semibold">Trail: how this was built<InfoTip text="Each step of the selection. A step marked added nothing did not change the result." term="Trail" /></h2>
      <ol className="space-y-1 text-sm">
        {q.data.steps.map((s) => (
          <li key={s.selection_id} className={s.selection_id === q.data!.current ? "font-medium" : ""}>
            Step {s.n}: {s.n === 1 ? `started with ${s.members.toLocaleString("en-US")} items` : s.adds_nothing ? "added nothing" : `added ${s.added_count.toLocaleString("en-US")} item${s.added_count === 1 ? "" : "s"}${s.added.length ? ` (${s.added.slice(0, 3).map((a) => a.label || a.type.replace(/_/g, " ")).join(", ")}${s.added_count > 3 ? ", …" : ""})` : ""}`}
            {s.level?.name ? `. ${s.level.name}${s.level_moved ? `: ${MOVED[s.level_moved].toLowerCase()}` : ""}.` : ". No level yet."}{" "}
            {s.selection_id === q.data!.current ? <span className="text-muted-foreground">(this page)</span>
              : <Link className="underline" to={`/cases/${caseId}/corroborate?q=${s.selection_id}`}>Open this step without the later ones</Link>}
          </li>
        ))}
      </ol>
    </section>
  )
}
