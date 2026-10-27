import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { countLine, processorRules, type Judgement } from "../lib/judgements"
import { JudgementMarker } from "./JudgementCalls"
import { useJudgementCounts, useJudgements } from "../hooks/use-judgements"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { SavedStatementPayments } from "./SavedStatementPayments"

const STATUS_CHOICES = [
  ["open", "Not yet checked"],
  ["", "All"],
  ["confirmed", "Looks right"],
  ["corrected", "Corrected"],
] as const
const STRENGTH_CHOICES = [
  ["", "Inferred and checked guesses"],
  ["inferred", "Inferred only"],
  ["proved", "Checked guesses only"],
] as const
const ORIGIN_CHOICES = [
  ["", "Hand entries and processor"],
  ["agent", "Hand entries (processing agent)"],
  ["processor", "Processor only"],
] as const

/**
 * Every place in this case where the processor made a less than straightforward decision. Nothing here is held:
 * a person spot-checks by rule or strength, says Looks right, or corrects the value through its usual edit.
 * Hand entries by the processing agent come first, then inferred values, then checked guesses.
 */
export function JudgementCallsPanel({ caseId }: { caseId: string }) {
  const [status, setStatus] = useState("open")
  const [strength, setStrength] = useState("")
  const [origin, setOrigin] = useState("")
  const [ruleId, setRuleId] = useState("")
  const [opened, setOpened] = useState<string | null>(null)
  const counts = useJudgementCounts(caseId)
  const query = useJudgements(caseId, { status, strength, origin, ruleId })
  const groups = useMemo(() => {
    const byStatement = new Map<string, Judgement[]>()
    for (const judgement of query.data || []) {
      const key = judgement.source_document_id || judgement.subject_id
      byStatement.set(key, [...(byStatement.get(key) || []), judgement])
    }
    return [...byStatement.entries()]
  }, [query.data])
  return (
    <section aria-label="Judgement calls" className="space-y-3">
      <header className="space-y-1">
        <h3 className="text-base font-semibold">Judgement calls</h3>
        <p className="text-sm text-muted-foreground">
          Places where the processor chose a value the page does not print outright, or chose between two
          readings. Nothing is held for these. Check any of them in the flow of work: Looks right keeps the rule as
          it is; a correction with its reason is sent back as a proposed improvement to the processor.
        </p>
        <p className="text-sm font-medium" role="status">
          {counts.data ? countLine(counts.data.case) || "No judgement calls recorded in this case." : ""}
        </p>
      </header>
      <div className="flex flex-wrap gap-2 text-sm" role="group" aria-label="Filter judgement calls">
        <label className="flex items-center gap-1">
          Status
          <select aria-label="Judgement status" className="rounded border p-1" value={status}
            onChange={(event) => setStatus(event.target.value)}>
            {STATUS_CHOICES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1">
          Strength
          <select aria-label="Judgement strength" className="rounded border p-1" value={strength}
            onChange={(event) => setStrength(event.target.value)}>
            {STRENGTH_CHOICES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1">
          Made by
          <select aria-label="Judgement origin" className="rounded border p-1" value={origin}
            onChange={(event) => setOrigin(event.target.value)}>
            {ORIGIN_CHOICES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1">
          Rule
          <select aria-label="Judgement rule" className="rounded border p-1" value={ruleId}
            onChange={(event) => setRuleId(event.target.value)}>
            <option value="">All rules</option>
            {(counts.data?.rules || []).map((rule) => (
              <option key={rule.rule_id} value={rule.rule_id} title={rule.rule_id}>
                {rule.label} ({rule.total})
              </option>
            ))}
          </select>
        </label>
      </div>
      {query.isPending ? (
        <p role="status">Loading judgement calls…</p>
      ) : query.isError ? (
        <p role="alert">{query.error.message}</p>
      ) : !groups.length ? (
        <p className="text-sm text-muted-foreground">No judgement calls match these filters.</p>
      ) : (
        <ul className="space-y-3">
          {groups.map(([documentId, items]) => (
            <li key={documentId} className="rounded border p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">
                  {items[0].filename || "Saved statement"}{" "}
                  <span className="text-muted-foreground">
                    · {countLine({
                      total: items.length,
                      inferred: items.filter((j) => j.strength === "inferred").length,
                    })}
                  </span>
                </p>
                {items[0].source_document_id && (
                  <Button size="sm" variant="outline" aria-expanded={opened === documentId}
                    onClick={() => setOpened(opened === documentId ? null : documentId)}>
                    {opened === documentId ? "Close the statement" : "Open the saved statement"}
                  </Button>
                )}
              </div>
              {items.map((judgement) => (
                <JudgementMarker
                  key={judgement.id}
                  caseId={caseId}
                  judgement={judgement}
                  onCorrect={() => setOpened(documentId)}
                />
              ))}
              {opened === documentId && items[0].source_document_id && (
                <div className="space-y-3 border-t pt-3">
                  <ImportedStatementDetails caseId={caseId} sourceId={items[0].source_document_id} withSource />
                  <SavedStatementPayments caseId={caseId} sourceId={items[0].source_document_id}
                    hasIncomplete={false} initiallyOpen />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <ProcessorRulesPanel caseId={caseId} />
    </section>
  )
}

/** The workspace button's label: the case's judgement calls not yet checked. */
export function JudgementCallsLabel({ caseId }: { caseId: string }) {
  const counts = useJudgementCounts(caseId)
  const open = Number(counts.data?.case.open || 0)
  return <>Judgement calls{open ? ` (${open} to check)` : ""}</>
}

/** Each rule's track record: how often a person confirmed it, corrected it, or has not checked it yet. */
export function ProcessorRulesPanel({ caseId }: { caseId: string }) {
  const [scope, setScope] = useState<"case" | "all_cases">("case")
  const query = useQuery({
    queryKey: ["financial-judgements", caseId, "rules"],
    queryFn: () => processorRules(caseId),
    retry: false,
    refetchOnWindowFocus: false,
  })
  const rows = (query.data?.[scope] || []).filter((rule) => rule.total > 0)
  return (
    <details className="rounded border p-3 text-sm" aria-label="Processor rules">
      <summary className="cursor-pointer font-medium">Processor rules</summary>
      <div className="mt-2 space-y-2">
        <p className="text-muted-foreground">
          How each rule's calls were answered. A correction proposes a change; the rule changes only after it is
          built, measured and released.
        </p>
        <div className="flex gap-2" role="group" aria-label="Rule counts for">
          <Button size="sm" variant={scope === "case" ? "primary" : "outline"} aria-pressed={scope === "case"}
            onClick={() => setScope("case")}>This case</Button>
          <Button size="sm" variant={scope === "all_cases" ? "primary" : "outline"}
            aria-pressed={scope === "all_cases"} onClick={() => setScope("all_cases")}>All cases</Button>
        </div>
        {query.isError ? (
          <p role="alert">{query.error.message}</p>
        ) : !rows.length ? (
          <p className="text-muted-foreground">{query.isPending ? "Loading…" : "No judgement calls yet."}</p>
        ) : (
          <table className="w-full text-left" aria-label="Rule track record">
            <thead>
              <tr>
                <th>Rule</th>
                <th className="text-right">Looks right</th>
                <th className="text-right">Corrected</th>
                <th className="text-right">Not yet checked</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((rule) => (
                <tr key={rule.rule_id} title={`${rule.rule_id} · ${rule.source}`}>
                  <td>{rule.label}</td>
                  <td className="text-right tabular-nums">{rule.confirmed}</td>
                  <td className="text-right tabular-nums">{rule.corrected}</td>
                  <td className="text-right tabular-nums">{rule.open}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </details>
  )
}
