import { RetainedFinancialTool } from "./FinancialNavigation"
import { useFinancialDraft } from "../stores/financial-drafts"
import { PaymentClaimComparison } from "./PaymentClaimComparison"
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"
import { candidateUrl } from "../lib/candidate-contract"
import {
  patternReview,
  patternTheory,
  type PatternReview,
} from "../lib/pattern-review"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import { InvestigationFilters } from "./InvestigationFilters"
import {
  useInvestigationScope,
  useAnalysisPopulation,
} from "../stores/investigation-scope"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
function PatternScreen({ caseId }: { caseId: string | undefined }) {
  const [params, setParams] = useInvestigationScope(caseId)
  const [population, setPopulation] = useAnalysisPopulation(caseId)
  const [crossAccount, setCrossAccount] = useFinancialDraft(
      caseId ?? "none",
      "pattern-cross-account",
      false
    ),
    [days, setDays] = useFinancialDraft(caseId ?? "none", "pattern-days", "3"),
    [threshold, setThreshold] = useFinancialDraft(
      caseId ?? "none",
      "pattern-threshold",
      ""
    ),
    [currency, setCurrency] = useFinancialDraft(
      caseId ?? "none",
      "pattern-currency",
      "GBP"
    )
  if (!caseId) return <p>Choose a case for pattern review.</p>
  return (
    <section aria-label="Financial pattern review" className="space-y-4 p-4">
      <h2 className="font-semibold">Patterns to investigate</h2>
      <p>
        Look for repeated names (even when amounts change), repeated amounts,
        money coming in and going out soon afterwards, or smaller payments that
        add up to an amount you choose. Run the checks below, open the matching
        payments, then record what you think they show.
      </p>
      <InvestigationFilters
        key={JSON.stringify(params)}
        caseId={caseId}
        initialParams={params}
        onApply={setParams}
      />
      <div className="flex gap-3">
        <label>
          Payments to check{" "}
          <select
            aria-label="Payments to check"
            value={population}
            onChange={(e) => setPopulation(e.target.value)}
            className="border bg-background p-2"
          >
            <option value="working">All imported payments</option>
            <option value="verified">Verified payments only</option>
          </select>
        </label>
        <label>
          Days between related payments{" "}
          <input
            aria-label="Screening window days"
            type="number"
            min="0"
            max="30"
            value={days}
            onChange={(e) => setDays(e.target.value)}
            className="w-20 border bg-background p-2"
          />
        </label>
      </div>
      <fieldset className="space-y-2 rounded border p-3">
        <legend>Optional split-payment check</legend>
        <p className="text-sm">
          Find smaller same-direction payments in one account whose combined
          amount reaches your threshold within the window. Leave the amount
          blank to skip this check. This is your screening criterion; it does
          not establish a reporting obligation or intent.
        </p>
        <div className="flex flex-wrap gap-3">
          <label>
            Threshold amount
            <input
              aria-label="Split-payment threshold amount"
              inputMode="decimal"
              maxLength={25}
              className="block border bg-background p-2"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
          </label>
          <label>
            Threshold currency
            <input
              aria-label="Split-payment threshold currency"
              maxLength={3}
              className="block w-24 border bg-background p-2"
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            />
          </label>
        </div>
      </fieldset>
      <label className="block">
        <input
          type="checkbox"
          aria-label="Screen paths between accounts"
          checked={crossAccount}
          onChange={(e) => setCrossAccount(e.target.checked)}
        />{" "}
        Check for money passing through several accounts or returning to its
        starting account (all accounts required)
      </label>
      <PatternScope
        key={JSON.stringify([
          caseId,
          params,
          population,
          days,
          threshold,
          currency,
          crossAccount,
        ])}
        caseId={caseId}
        params={params}
        population={population}
        days={days}
        threshold={threshold}
        currency={currency}
        crossAccount={crossAccount}
      />
    </section>
  )
}
function PatternScope({
  caseId,
  params,
  population,
  days,
  threshold,
  currency,
  crossAccount,
}: {
  caseId: string
  params: LedgerQueryParams
  population: string
  days: string
  threshold: string
  currency: string
  crossAccount: boolean
}) {
  const [source, setSource] = useState<string | null>(null),
    [page, setPage] = useState(0)
  const load = useMutation({
    retry: false,
    mutationFn: async () => {
      const thresholdMinor = threshold.trim()
        ? correctionMinor(threshold, currency)
        : null
      if (threshold.trim() && (!thresholdMinor || BigInt(thresholdMinor) <= 0n))
        throw Error(
          "Enter a positive exact threshold amount and a supported currency."
        )
      const q = new URLSearchParams({
        population,
        window_days: days,
        cross_account: String(crossAccount),
      })
      if (thresholdMinor) {
        q.set("threshold_minor", thresholdMinor)
        q.set("threshold_currency", currency)
      }
      if (params.accountId) q.set("account_id", params.accountId)
      if (params.startDate) q.set("start_date", params.startDate)
      if (params.endDate) q.set("end_date", params.endDate)
      const value = patternReview.parse(
        await fetchAPI(`${candidateUrl("pattern-review", caseId)}&${q}`, {
          timeout: 120000,
        })
      )
      if (
        value.case_id !== caseId ||
        value.account_id !== (params.accountId ?? null) ||
        value.start_date !== (params.startDate ?? null) ||
        value.end_date !== (params.endDate ?? null) ||
        value.population !== population ||
        value.window_days !== Number(days) ||
        value.cross_account !== crossAccount ||
        value.threshold_minor !== thresholdMinor ||
        value.threshold_currency !== (thresholdMinor ? currency : null)
      )
        throw Error("Pattern review returned a different scope.")
      return value
    },
  })
  return (
    <div className="space-y-4">
      <Button
        disabled={load.isPending || !/^\d+$/.test(days) || Number(days) > 30}
        onClick={() => {
          setPage(0)
          load.reset()
          load.mutate()
        }}
      >
        {load.isPending ? "Checking payments…" : "Find patterns"}
      </Button>
      {load.isError && <p role="alert">{load.error.message}</p>}
      {load.data && (
        <>
          <details className="text-sm">
            <summary className="cursor-pointer">
              What these checks cover
            </summary>
            <p>{load.data.limitation}</p>
          </details>
          <p>
            {load.data.reviewed_rows} current readings reviewed;{" "}
            {load.data.date_unavailable_ids.length} readings lack transaction
            timing for these screens. {load.data.hypotheses.length} candidates.
          </p>
          {!load.data.hypotheses.length && (
            <p>
              No candidates under the selected rules. This is not a finding that
              no relevant pattern exists; missing evidence and other patterns
              are not covered.
            </p>
          )}
          {load.data.hypotheses.slice(page * 10, page * 10 + 10).map((h) => (
            <PatternCard
              key={load.data!.snapshot_sha256 + h.id}
              scope={load.data!}
              hypothesis={h}
              onSource={setSource}
            />
          ))}
          {load.data.hypotheses.length > 10 && (
            <div className="flex gap-2">
              <Button disabled={!page} onClick={() => setPage(page - 1)}>
                Previous patterns
              </Button>
              <span>
                Page {page + 1} of {Math.ceil(load.data.hypotheses.length / 10)}
              </span>
              <Button
                disabled={(page + 1) * 10 >= load.data.hypotheses.length}
                onClick={() => setPage(page + 1)}
              >
                Next patterns
              </Button>
            </div>
          )}
        </>
      )}
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </div>
  )
}
function PatternCard({
  scope,
  hypothesis: h,
  onSource,
}: {
  scope: PatternReview
  hypothesis: PatternReview["hypotheses"][number]
  onSource: (id: string) => void
}) {
  const [title, setTitle] = useFinancialDraft(
      scope.case_id,
      "pattern-title:" + h.id,
      ""
    ),
    [reason, setReason] = useFinancialDraft(
      scope.case_id,
      "pattern-note:" + h.id,
      ""
    ),
    [validation, setValidation] = useState("")
  const save = useCreateCaseworkEntry(scope.case_id)
  const submit = () => {
    try {
      const input = patternTheory(scope, h, title, reason)
      setValidation("")
      save.mutate(input)
    } catch (error) {
      setValidation(
        error instanceof Error
          ? error.message
          : "Hypothesis could not be prepared."
      )
    }
  }
  return (
    <article className="space-y-3 rounded border p-4">
      <h3 className="font-semibold">
        {h.kind === "repeated_counterparty"
          ? `Repeated payments: ${h.counterparty_label}`
          : h.kind === "repeated_equal_amount"
            ? "Repeated equal amount"
            : h.kind === "equal_amount_in_and_out"
              ? "Equal amount in and out"
              : h.kind === "possible_transfer_chain"
                ? "Possible chain between accounts"
                : h.kind === "possible_return_flow"
                  ? "Possible return to the starting account"
                  : "Smaller payments reach selected threshold"}{" "}
        · {h.account_label} · {correctionMoney(h.amount_minor, h.currency)}
      </h3>
      <p>{h.explanation}</p>
      {h.kind === "repeated_counterparty" && (
        <p className="text-sm">
          The amount above is the total of the {h.sources.length} payments shown
          below.
        </p>
      )}
      {h.transfer_pairs && (
        <p>
          {h.transfer_pairs.length} candidate transfers, supported by{" "}
          {h.sources.length} postings. The amount above is the equal amount per
          transfer; it is not a sum or a traced allocation.
        </p>
      )}
      {h.kind === "split_payment_threshold" && (
        <p>
          {h.sources.length} payments; combined amount shown above. Selected
          threshold: {correctionMoney(scope.threshold_minor!, h.currency)}.
        </p>
      )}
      <p>
        {h.gap_days} days apart. {h.limitation}
      </p>
      {h.sources.map((s, i) => (
        <div key={s.row.key}>
          <p>
            {s.row.account_label} · {s.row.chronology_date} ·{" "}
            {s.row.direction === "credit" ? "Credit" : "Debit"} ·{" "}
            {correctionMoney(s.row.amount_minor, s.row.currency)} ·{" "}
            {s.row.description}
          </p>
          <Button variant="outline" onClick={() => onSource(s.row.key)}>
            Open payment {i + 1}
          </Button>
        </div>
      ))}
      {save.data ? (
        <p role="status">
          Saved in Findings as a proposed explanation: {save.data.title}.{" "}
          <a
            className="underline"
            href={`/cases/${encodeURIComponent(scope.case_id)}/workspace`}
          >
            Open Workspace
          </a>
        </p>
      ) : (
        <fieldset
          disabled={save.isPending || save.isError}
          className="space-y-2"
        >
          <legend>Record your explanation</legend>
          <label className="block">
            Title
            <input
              aria-label={`Theory title ${h.id}`}
              className="block w-full border bg-background p-2"
              maxLength={255}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="block">
            Reasoning and alternative explanations
            <textarea
              aria-label={`Hypothesis reasoning ${h.id}`}
              className="block w-full border bg-background p-2"
              maxLength={4096}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <Button
            disabled={
              !title.trim() ||
              !reason.trim() ||
              h.sources.some((s) => !s.source.evidence_file_id)
            }
            onClick={submit}
          >
            {save.isPending
              ? "Saving…"
              : "Save explanation and supporting payments"}
          </Button>
        </fieldset>
      )}
      {validation && <p role="alert">{validation}</p>}
      {save.isError && (
        <p role="alert">
          {save.error.message} Check Workspace before retrying; the response may
          have been lost after saving.
        </p>
      )}
    </article>
  )
}

export function FinancialPatternReview({
  caseId,
}: {
  caseId: string | undefined
}) {
  const [mode, setMode] = useState("patterns")
  return (
    <div>
      <div className="flex gap-2 p-4">
        <Button
          variant={mode === "patterns" ? "primary" : "outline"}
          onClick={() => setMode("patterns")}
        >
          Review patterns
        </Button>
        <Button
          variant={mode === "claims" ? "primary" : "outline"}
          onClick={() => setMode("claims")}
        >
          Compare payment claim
        </Button>
      </div>
      {caseId && (
        <RetainedFinancialTool active={mode === "claims"}>
          <PaymentClaimComparison key={caseId} caseId={caseId} />
        </RetainedFinancialTool>
      )}
      <RetainedFinancialTool active={mode === "patterns"}>
        <PatternScreen key={caseId} caseId={caseId} />
      </RetainedFinancialTool>
    </div>
  )
}
