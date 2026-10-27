import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  ORIGIN_LABELS,
  STATUS_LABELS,
  STRENGTH_LABELS,
  countLine,
  processorRules,
  type Judgement,
} from "../lib/judgements"
import { AccountMultiSelect } from "./AccountMultiSelect"
import { JudgementMarker } from "./JudgementCalls"
import { useJudgementCounts, useJudgementSearch } from "../hooks/use-judgements"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { SavedStatementPayments } from "./SavedStatementPayments"

const PAGE_SIZE = 50
const STATUSES = ["open", "confirmed", "corrected"] as const
const STRENGTHS = ["inferred", "proved"] as const
const ORIGINS = ["agent", "processor"] as const

function ChipRow({
  label,
  allLabel,
  value,
  choices,
  counts,
  onChoose,
}: {
  label: string
  allLabel: string
  value: string
  choices: { value: string; label: string; title?: string }[]
  counts: Record<string, number> | undefined
  onChoose: (value: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label={label}>
      <span>{label}:</span>
      <Button size="sm" variant={value ? "outline" : "primary"} aria-pressed={!value} onClick={() => onChoose("")}>
        {allLabel} ({counts?.all || 0})
      </Button>
      {choices.map((choice) => (
        <Button
          key={choice.value}
          size="sm"
          title={choice.title}
          variant={value === choice.value ? "primary" : "outline"}
          aria-pressed={value === choice.value}
          onClick={() => onChoose(value === choice.value ? "" : choice.value)}
        >
          {choice.label} ({counts?.[choice.value] || 0})
        </Button>
      ))}
    </div>
  )
}

/**
 * Every place in this case where the processor made a less than straightforward decision. Nothing here is held:
 * a person searches and filters them like the review queue, says Looks right, or corrects the value through its
 * usual edit. Hand entries by the processing agent come first, then inferred values, then checked guesses.
 */
export function JudgementCallsPanel({ caseId }: { caseId: string }) {
  const [params, setParams] = useSearchParams()
  const list = (key: string) => (params.get(key) || "").split(",").filter(Boolean)
  const statusParam = params.get("jStatus") || "open"
  const status = statusParam === "all" ? "" : statusParam
  const type = params.get("jType") || ""
  const strength = params.get("jStrength") || ""
  const origin = params.get("jBy") || ""
  const fileIds = list("jFiles")
  const accountIds = list("jAccounts")
  const offset = Math.max(0, Number(params.get("jPage") || 0) * PAGE_SIZE)
  const urlSearch = params.get("jq") || ""
  const [search, setSearch] = useState(urlSearch)
  const [opened, setOpened] = useState<string | null>(null)
  const update = (changes: Record<string, string | string[]>, keepPage = false) =>
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(changes)) {
        const text = Array.isArray(value) ? value.join(",") : value
        if (text) next.set(key, text)
        else next.delete(key)
      }
      if (!keepPage) next.delete("jPage")
      return next
    })
  // Debounced: the search runs on the server once typing pauses.
  useEffect(() => {
    if (search === urlSearch) return
    const timer = window.setTimeout(() => update({ jq: search }), 300)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])
  const counts = useJudgementCounts(caseId)
  const query = useJudgementSearch(caseId, {
    q: urlSearch,
    status: status ? [status] : [],
    category: type ? [type] : [],
    strength: strength ? [strength] : [],
    origin: origin ? [origin] : [],
    fileIds,
    accountIds,
    offset,
    limit: PAGE_SIZE,
  })
  const page = query.data
  const groups = useMemo(() => {
    const byStatement = new Map<string, Judgement[]>()
    for (const judgement of page?.items || []) {
      const key = judgement.source_document_id || judgement.subject_id
      byStatement.set(key, [...(byStatement.get(key) || []), judgement])
    }
    return [...byStatement.entries()]
  }, [page?.items])
  const facets = page?.facets
  const total = page?.total || 0
  const shown = page?.items.length || 0
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
      <input
        aria-label="Search judgement calls"
        placeholder="Search file names, accounts, periods, payments or the call itself"
        className="w-full rounded border bg-background p-2"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {fileIds.length > 0 && (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded border p-2 text-sm">
          <span>
            Showing the {fileIds.length} selected {fileIds.length === 1 ? "file" : "files"}
            {page?.files.length ? `: ${page.files.map((file) => file.label).join(", ")}` : ""}.
          </span>
          <Button size="sm" variant="outline" onClick={() => update({ jFiles: "" })}>
            Show the whole case
          </Button>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <AccountMultiSelect
          label="Accounts"
          allLabel="All accounts"
          options={page?.accounts || []}
          selected={accountIds}
          onChange={(values) => update({ jAccounts: values })}
        />
      </div>
      <ChipRow
        label="Show"
        allLabel="All"
        value={status}
        choices={STATUSES.map((value) => ({ value, label: STATUS_LABELS[value] }))}
        counts={facets?.status}
        onChoose={(value) => update({ jStatus: value || "all" })}
      />
      <ChipRow
        label="Type"
        allLabel="All types"
        value={type}
        choices={(page?.categories || []).map((category) => ({
          value: category.key,
          label: category.label,
          title: (page?.rules || [])
            .filter(([, , kind]) => kind === category.key)
            .map(([rule, label]) => `${label} (${rule})`)
            .join("; "),
        }))}
        counts={facets?.category}
        onChoose={(value) => update({ jType: value })}
      />
      <ChipRow
        label="Strength"
        allLabel="Both"
        value={strength}
        choices={STRENGTHS.map((value) => ({ value, label: STRENGTH_LABELS[value] }))}
        counts={facets?.strength}
        onChoose={(value) => update({ jStrength: value })}
      />
      <ChipRow
        label="Made by"
        allLabel="Both"
        value={origin}
        choices={ORIGINS.map((value) => ({ value, label: ORIGIN_LABELS[value] }))}
        counts={facets?.origin}
        onChoose={(value) => update({ jBy: value })}
      />
      {query.isPending ? (
        <p role="status">Loading judgement calls…</p>
      ) : query.isError ? (
        <p role="alert">{query.error.message}</p>
      ) : !groups.length ? (
        <p className="text-sm text-muted-foreground">No judgement calls match these filters.</p>
      ) : (
        <ul className="space-y-3" aria-busy={query.isFetching}>
          {groups.map(([documentId, items]) => (
            <li key={documentId} className="rounded border p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">
                  {items[0].filename || "Saved statement"}
                  {items[0].period_start ? ` · ${items[0].period_start} to ${items[0].period_end || "?"}` : ""}
                  {items[0].account_label ? ` · ${items[0].account_label}` : ""}{" "}
                  <span className="text-muted-foreground">
                    · {countLine({
                      total: items.length,
                      inferred: items.filter((j) => j.strength === "inferred").length,
                    })}
                  </span>
                </p>
                <div className="flex gap-2">
                  {items[0].evidence_file_id && !fileIds.includes(items[0].evidence_file_id) && (
                    <Button size="sm" variant="ghost"
                      onClick={() => update({ jFiles: [items[0].evidence_file_id || ""] })}>
                      Only this file
                    </Button>
                  )}
                  {items[0].source_document_id && (
                    <Button size="sm" variant="outline" aria-expanded={opened === documentId}
                      onClick={() => setOpened(opened === documentId ? null : documentId)}>
                      {opened === documentId ? "Close the statement" : "Open the saved statement"}
                    </Button>
                  )}
                </div>
              </div>
              {items.map((judgement) => (
                <JudgementMarker
                  key={judgement.id}
                  caseId={caseId}
                  judgement={judgement}
                  defaultOpen={items.length <= 2}
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
      {total > PAGE_SIZE || offset > 0 ? (
        <nav aria-label="Pages of this list" className="flex flex-wrap items-center gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={offset === 0}
            onClick={() => update({ jPage: String(offset / PAGE_SIZE - 1 || "") }, true)}>
            Previous {PAGE_SIZE}
          </Button>
          <span role="status" aria-label="Shown of this list">
            Showing {shown ? offset + 1 : 0}–{offset + shown} of {total}
          </span>
          <Button size="sm" variant="outline" disabled={offset + PAGE_SIZE >= total}
            onClick={() => update({ jPage: String(offset / PAGE_SIZE + 1) }, true)}>
            Next {PAGE_SIZE}
          </Button>
        </nav>
      ) : null}
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
