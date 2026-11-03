import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { agentProposalKeys, fetchTheoryAlternatives, runRedCell } from "../agent-proposals"

/**
 * Red cell: for one theory, a model other than the case agent's reads the theory's evidence without the theory
 * (its title and text are not sent; the names it uses are replaced by Person A, Person B) and lists other
 * explanations. Each one waits in Agent proposals for a person. The counts of what people accepted stay here.
 */
export function RedCellPanel({ caseId, theoryId, canEdit }: { caseId: string; theoryId: string; canEdit: boolean }) {
  const client = useQueryClient()
  const tally = useQuery({
    queryKey: [...agentProposalKeys.all(caseId), "red-cell", theoryId],
    queryFn: () => fetchTheoryAlternatives(caseId, theoryId),
  })
  const run = useMutation({
    mutationFn: () => runRedCell(caseId, theoryId),
    onSuccess: () => client.invalidateQueries({ queryKey: agentProposalKeys.all(caseId) }),
  })
  const result = run.data
  return (
    <section className="space-y-2 rounded-lg border border-border p-3 text-sm" aria-label="Other explanations (red cell)">
      <h3 className="text-sm font-semibold">Other explanations (red cell)</h3>
      <p className="text-xs text-muted-foreground">
        A different model reads this theory's linked evidence without being shown the theory, and lists explanations
        that fit the same facts, innocent ones included. Each one waits in Agent proposals for a person to accept or
        reject.
      </p>
      {tally.data && (
        <p data-testid="red-cell-tally">
          From earlier sweeps of this theory: {tally.data.total} proposed, {tally.data.accepted} accepted by a person,{" "}
          {tally.data.rejected} rejected, {tally.data.waiting} waiting.
          {tally.data.truncated ? " (Counted over the latest 100 alternatives in this case.)" : ""}
        </p>
      )}
      {canEdit && (
        <Button size="sm" variant="outline" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Reading on another model… (up to three minutes)" : "Look for other explanations"}
        </Button>
      )}
      {result && (
        <div role="status" className="space-y-1" data-testid="red-cell-result">
          <p>
            {result.model.model_id} (the case agent uses {result.agent_model.model_id}) read {result.facts}{" "}
            {result.facts === 1 ? "fact" : "facts"}, with {result.names_neutralised}{" "}
            {result.names_neutralised === 1 ? "name" : "names"} from the theory replaced. It gave {result.returned}{" "}
            {result.returned === 1 ? "explanation" : "explanations"}; {result.recorded} recorded as proposals
            {result.refused.length ? `, ${result.refused.length} not recorded` : ""}.
          </p>
          {!!result.refused.length && (
            <ul className="list-disc pl-5 text-xs text-muted-foreground">
              {result.refused.map((r, i) => (
                <li key={i}>
                  {r.title || "Untitled"}: {r.why}
                </li>
              ))}
            </ul>
          )}
          <Link className="font-medium underline underline-offset-2" to={`/cases/${encodeURIComponent(caseId)}/workspace?view=proposals`}>
            Review them in Agent proposals
          </Link>
        </div>
      )}
      {run.error && <p role="alert">{run.error.message}</p>}
    </section>
  )
}
