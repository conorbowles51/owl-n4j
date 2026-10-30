import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  ORIGIN_LABELS,
  STATUS_LABELS,
  STRENGTH_LABELS,
  PRIORITY_LABELS,
  countLine,
  judgementExportUrl,
  processorRules,
  type Judgement,
} from "../lib/judgements"
import { downloadProtectedFile } from "@/lib/protected-file"
import { AccountMultiSelect } from "./AccountMultiSelect"
import { JudgementMarker, PriorityLabel, PriorityLegend } from "./JudgementCalls"
import { priorityRowClass } from "../lib/judgements"
import { useJudgementCounts, useJudgementSearch } from "../hooks/use-judgements"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { SavedStatementPayments } from "./SavedStatementPayments"
import { InfoTip } from "./InfoTip"
import { CategoryRulesTable } from "./CategoryRules"

const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.025em" }

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
  choices: { value: string; label: string; title?: string; glyph?: string }[]
  counts: Record<string, number> | undefined
  onChoose: (value: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-sm" role="group" aria-label={label}>
      <span className="w-20 shrink-0 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{label}</span>
      {[{ value: "", label: allLabel, glyph: "" } as { value: string; label: string; title?: string; glyph?: string }, ...choices].map((choice) => {
        const on = choice.value ? value === choice.value : !value
        return (
          <button
            key={choice.value || "all"}
            type="button"
            title={choice.title}
            aria-pressed={on}
            onClick={() => onChoose(choice.value && value !== choice.value ? choice.value : "")}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-semibold transition-colors ${on ? "bg-[#14161b] text-white dark:bg-[#f7f7f8] dark:text-[#0b0c0f]" : "bg-card text-foreground shadow-[0_1px_0_#e4e3df] hover:bg-muted dark:border"}`}
          >
            {choice.glyph && <span aria-hidden="true">{choice.glyph}</span>}
            {choice.label} ({(choice.value ? counts?.[choice.value] : counts?.all) || 0})
          </button>
        )
      })}
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
  const tier = params.get("jPriority") || ""
  const type = params.get("jType") || ""
  const strength = params.get("jStrength") || ""
  const origin = params.get("jBy") || ""
  const fileIds = list("jFiles")
  const accountIds = list("jAccounts")
  const offset = Math.max(0, Number(params.get("jPage") || 0) * PAGE_SIZE)
  const urlSearch = params.get("jq") || ""
  const [search, setSearch] = useState(urlSearch)
  const [opened, setOpened] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
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
  const filter = {
    q: urlSearch,
    status: status ? [status] : [],
    priority: tier ? [tier] : [],
    category: type ? [type] : [],
    strength: strength ? [strength] : [],
    origin: origin ? [origin] : [],
    fileIds,
    accountIds,
  }
  const query = useJudgementSearch(caseId, { ...filter, offset, limit: PAGE_SIZE })
  const page = query.data
  // The server's order is focus-first (priority, then inferred, then amount); a statement's calls are grouped
  // within their tier, so a "When convenient" call never rides up the list beside a "Check first" one.
  const groups = useMemo(() => {
    const byStatement = new Map<string, Judgement[]>()
    for (const judgement of page?.items || []) {
      const key = `${judgement.priority}:${judgement.source_document_id || judgement.subject_id}`
      byStatement.set(key, [...(byStatement.get(key) || []), judgement])
    }
    return [...byStatement.entries()]
  }, [page?.items])
  const facets = page?.facets
  const caseTotal = Number(counts.data?.case.total || 0)
  const checked = Number(counts.data?.case.confirmed || 0) + Number(counts.data?.case.corrected || 0)
  const checkFirst = Number(counts.data?.case.priority_1 || 0)
  // The rule types inside the chosen type, with their case-wide counts.
  const typeRules = type
    ? (page?.rules || [])
        .filter(([, , kind]) => kind === type)
        .map(([rule, label]) => ({ rule, label, total: counts.data?.rules.find((item) => item.rule_id === rule)?.total ?? 0 }))
    : []
  const total = page?.total || 0
  const shown = page?.items.length || 0
  return (
    <section aria-label="Judgement calls" className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[#b41624] dark:text-[#e33b4c]">Spot-check Loupe</span>
          <h3 className="text-2xl font-semibold leading-tight sm:text-[30px]" style={heading}>
            Judgement calls
            {caseTotal ? ` · ${caseTotal.toLocaleString()} on this case.` : ""}
            {caseTotal ? (
              <span className="block text-muted-foreground">
                You've checked {checked.toLocaleString()}.
                {checkFirst ? ` Start with the ${checkFirst.toLocaleString()} to check first: they can change the money itself.` : ""}
              </span>
            ) : null}
            <InfoTip text="Places where the processor chose a value the page does not print outright, or chose between two readings. Nothing is held for these. Check any of them in the flow of work: Looks right keeps the rule as it is; a correction with its reason is sent back as a proposed improvement to the processor." />
          </h3>
          <p className="text-sm font-medium" role="status">
            {counts.data ? countLine(counts.data.case) || "No judgement calls recorded in this case." : ""}
          </p>
        </div>
        <label className="flex w-full items-center gap-2 rounded-lg border bg-card px-3 sm:w-[380px]">
          <span aria-hidden="true" className="text-muted-foreground">⌕</span>
          <input
            type="search"
            aria-label="Search judgement calls"
            placeholder="Search file names, accounts, periods, payments or the call itself"
            className="w-full bg-transparent py-2 outline-none"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
      </header>
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
      <PriorityLegend
        counts={facets?.priority}
        value={tier}
        onChoose={(value) => update({ jPriority: value })}
      />
      <ChipRow
        label="Show"
        allLabel="All"
        value={status}
        choices={STATUSES.map((value) => ({ value, label: STATUS_LABELS[value], glyph: { open: "○", confirmed: "✓", corrected: "✕" }[value] }))}
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
      {type && (
        <p className="pl-[5.5rem] text-[13px] text-muted-foreground" aria-label="Rule types in this type">
          In this type (whole case):{" "}
          {typeRules.length
            ? typeRules.map((item) => `${item.label} ${item.total}`).join(" · ")
            : "no rule types listed"}
        </p>
      )}
      <ChipRow
        label="Strength"
        allLabel="Both"
        value={strength}
        choices={STRENGTHS.map((value) => ({ value, label: STRENGTH_LABELS[value], glyph: value === "inferred" ? "◐" : "●" }))}
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
            <li key={documentId} data-testid="judgement-group" data-priority={items[0].priority}
              className={`space-y-2 rounded-[14px] p-4 shadow-[0_1px_0_#e4e3df,0_8px_24px_rgba(20,22,27,.05)] dark:border ${priorityRowClass(items[0].priority)}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[15px] font-semibold" style={heading}>
                  <PriorityLabel priority={items[0].priority} className="mr-2 align-middle" />
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
                  hidePriority
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
      <div className="space-y-1">
        <Button
          size="sm"
          variant="outline"
          disabled={!total}
          onClick={() => {
            setDownloadError(null)
            void downloadProtectedFile(judgementExportUrl(caseId, filter), `judgement-calls-${caseId.slice(0, 8)}.csv`)
              .catch(() => setDownloadError("The list could not be prepared. Try again."))
          }}
        >
          Download these {total.toLocaleString()} calls (CSV)
        </Button>
        <p className="text-xs text-muted-foreground">
          Every call matching these filters, in this order, with its priority
          {tier ? ` (${PRIORITY_LABELS[tier]} only)` : ""}.
        </p>
        {downloadError && <p className="text-xs text-destructive">{downloadError}</p>}
      </div>
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
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-[14px] bg-card p-3 text-sm dark:border" aria-label="Processor rules" role="group">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 font-semibold hover:bg-muted"
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        Processor rules{query.data ? ` (${rows.length})` : ""}
      </button>
      <div className={open ? "mt-2 space-y-2" : "hidden"}>
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
        <h4 className="pt-2 font-semibold">Category rules people made</h4>
        <CategoryRulesTable caseId={caseId} />
      </div>
    </div>
  )
}
