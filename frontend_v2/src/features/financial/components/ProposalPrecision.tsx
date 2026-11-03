import { useQuery } from "@tanstack/react-query"
import { proposalPrecision, type ProposalPrecision as Precision } from "../lib/judgements"

const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.025em" }

function Block({ title, data }: { title: string; data: Precision["case"] }) {
  const c = data.confirmations
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {!data.kinds.length ? (
        <p className="text-muted-foreground">No proposals from the case agent yet.</p>
      ) : (
        <table className="w-full text-left text-[13px]" aria-label={`${title}: proposals by kind`}>
          <thead className="text-muted-foreground">
            <tr>
              <th className="py-1 pr-3 font-medium">Kind</th>
              <th className="py-1 pr-3 font-medium">Waiting</th>
              <th className="py-1 pr-3 font-medium">Accepted</th>
              <th className="py-1 pr-3 font-medium">Corrected</th>
              <th className="py-1 pr-3 font-medium">Rejected</th>
              <th className="py-1 font-medium">By week answered (accepted / corrected / rejected)</th>
            </tr>
          </thead>
          <tbody>
            {data.kinds.map((k) => (
              <tr key={k.kind} className="border-t align-top" data-testid="precision-kind" data-kind={k.kind}>
                <td className="py-1 pr-3">{k.label}</td>
                <td className="py-1 pr-3">{k.open}</td>
                <td className="py-1 pr-3">{k.accepted}</td>
                <td className="py-1 pr-3">{k.corrected}</td>
                <td className="py-1 pr-3">{k.rejected}</td>
                <td className="py-1">
                  {k.weeks.length
                    ? k.weeks.map((w) => `${w.week}: ${w.accepted} / ${w.corrected} / ${w.rejected}`).join(" · ")
                    : "none answered yet"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p data-testid="precision-confirmations">
        Accepted proposals: {c.total}. After opening a cited source: {c.with_source_opened}. Without opening one
        (through the API): {c.without_source_opened}.
        {c.total > c.with_source_opened + c.without_source_opened
          ? ` Not recorded either way: ${c.total - c.with_source_opened - c.without_source_opened}.`
          : ""}
      </p>
    </div>
  )
}

/** How the case agent's proposals fared with the people who decided them, per kind and per week. Counts only. */
export function ProposalPrecisionPanel({ caseId }: { caseId: string }) {
  const query = useQuery({ queryKey: ["financial-judgements", caseId, "proposal-precision"], queryFn: () => proposalPrecision(caseId) })
  return (
    <section
      aria-label="How the case agent's proposals fared"
      className="space-y-3 rounded-[14px] p-4 text-sm shadow-[0_1px_0_#e4e3df,0_8px_24px_rgba(20,22,27,.05)] dark:border"
    >
      <h2 className="text-[15px] font-semibold" style={heading}>How the case agent's proposals fared</h2>
      <p className="text-muted-foreground">
        Every proposal waits for a person. These are the answers people gave, counted as recorded.
      </p>
      {query.isPending ? (
        <p role="status">Loading…</p>
      ) : query.isError ? (
        <p role="alert">{query.error.message}</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Block title="This case" data={query.data.case} />
          <Block title="Every case you are a member of" data={query.data.all_cases} />
        </div>
      )}
    </section>
  )
}
