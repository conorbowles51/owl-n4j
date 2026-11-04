import { useMemo, useRef, useState } from "react"
import { ArrowRight, Files, BookOpenCheck, WalletCards } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useCaseworkEntries } from "@/features/workspace/hooks/use-casework"
import { useFinancialStore } from "../stores/financial.store"
import { PaymentTotalsView } from "./InvestigationTransactionTable"
import { WorkspaceScope } from "./InvestigationWorkspaceParts"
import { useStatementRegister } from "../hooks/use-statement-register"
import { MoneyConnectionsView } from "./InvestigatorFollowMoney"
import { PaymentComparison } from "./PaymentComparison"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { OverviewStatementCoverage } from "./OverviewStatementCoverage"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useJudgementCounts } from "../hooks/use-judgements"
import { useLedgerOverview, useLedgerOverviewPanels, usePanelFigureKeys } from "../hooks/use-ledger-overview"
import { unnamedFigureId, type FigureGroup, type PanelFigure } from "../lib/overview-panels"
import { compactMoney, minorToNumber } from "../lib/category-palette"
import { formatLedgerAmount } from "../lib/ledger-format"
import { overviewFigures } from "../lib/overview-figures"
import { InfoTip } from "./InfoTip"

const heading = { fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif", letterSpacing: "-0.025em" }
const eyebrow = "font-mono text-[11px] uppercase tracking-[0.12em]"
const card = { boxShadow: "0 1px 0 #e4e3df, 0 8px 24px rgba(20,22,27,.05)" }
const n = (value: number) => value.toLocaleString()
const plural = (count: number, one: string, many = `${one}s`) => `${n(count)} ${count === 1 ? one : many}`
const monthName = (day: string) =>
  new Date(`${day}T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" })
type Step = { name: string; detail: string; done: boolean }
/** How many payments a figure of the connections panel shows. */
function drawnCount(groups: FigureGroup[], figure: PanelFigure): number {
  if (figure.list === "comparisons") return 0
  const group = groups.find((item) => item.group === figure.group)
  if (figure.list === "account") return group?.accounts.find((item) => item.id === figure.id)?.count ?? 0
  if (figure.list === "unnamed")
    return group?.unnamed.find((item) => unnamedFigureId(item) === figure.id)?.count ?? 0
  return group?.names.find((item) => item.id === figure.id)?.[figure.list].count ?? 0
}

// A query keeps its last answer when a background refetch fails (isError is then true with data still held).
// Everything here is shown from the answer held; "could not be loaded" is only for a query that has none.
const held = (query: { data: unknown }) => query.data !== undefined
const failed = (query: { data: unknown; isError: boolean }) => query.isError && query.data === undefined

export function InvestigatorOverview({
  caseId,
  active = true,
}: {
  caseId: string
  active?: boolean
}) {
  const register = useStatementRegister(caseId, false, [], false, active)
  const findings = useCaseworkEntries(caseId, {
    tag: "financial",
    limit: 4,
    offset: 0,
  })
  const { canEdit } = useFinancialAccess()
  // The top card's figures and the panels below come from the server (the same figures over the same rows), so the
  // Overview does not download every payment (d5b330d1: 27,673 payments, a 64 MB answer).
  const totals = useLedgerOverview(caseId, active)
  const panels = useLedgerOverviewPanels(caseId, active)
  const panelTotals = useMemo(() => {
    const figures = panels.data?.totals
    if (!figures) return null
    const inventory = figures.inventory
    return {
      inventory: {
        accounts: inventory.accounts.map((account) => ({ ...account, currencies: new Set(account.currencies) })),
        banks: inventory.banks,
        currencies: inventory.currencies,
        first: inventory.first,
        last: inventory.last,
        undated: inventory.undated,
        unknownBanks: inventory.unknown_banks,
        unidentifiedCounterparties: inventory.unidentified_counterparties,
      },
      totals: new Map(figures.groups.map((group) => [group.group, {
        credit: BigInt(group.credit), debit: BigInt(group.debit), count: group.count, accountCount: group.accounts,
      }])),
    }
  }, [panels.data])
  const comparisons = panels.data?.comparisons
  const { payments, unknownDates, uncategorised, accountCount, currencyCounts, currencies, money: moneyBy, firstDay, lastDay } =
    useMemo(() => overviewFigures(totals.data), [totals.data])
  const totalsReady = held(totals)
  const span = firstDay && lastDay ? `${monthName(firstDay)} – ${monthName(lastDay)}` : "No dated payments"
  const [open, setOpen] = useState<{ ids: string[]; title: string } | null>(
    null
  )
  // The panels draw counts; the payments behind a figure are read when it is opened (usePanelFigureKeys). The
  // line below says so while they are read, and names a failure with a retry.
  const figureKeys = usePanelFigureKeys(caseId)
  const [opening, setOpening] = useState<
    { figure: PanelFigure; title: string; drawn: number; error?: string } | null
  >(null)
  const openingNow = useRef<PanelFigure | null>(null)
  const openFigure = (figure: PanelFigure, title: string, drawn: number) => {
    openingNow.current = figure
    setOpening({ figure, title, drawn })
    const failed = (error: string) => {
      if (openingNow.current === figure) setOpening({ figure, title, drawn, error })
    }
    figureKeys(figure, drawn).then(
      (ids) => {
        if (openingNow.current !== figure) return
        if (ids === null) return failed("these figures changed since they were drawn and are being updated; choose it again")
        openingNow.current = null
        setOpening(null)
        setOpen({ ids, title })
      },
      (error: unknown) => failed(error instanceof Error ? error.message : String(error))
    )
  }

  const [finding, setFinding] = useState(false)
  const navigate = useFinancialStore((state) => state.setMainView)
  const go = useNavigate()
  const judgements = useJudgementCounts(caseId)
  const [chosenCurrency, setChosenCurrency] = useState("")
  const files = register.files.data ?? []
  const importedIds = new Set(
    register.imports.data?.files
      .filter(
        (file) => file.current_transactions > 0 || file.periods.length > 0
      )
      .map((file) => file.evidence_file_id)
  )
  const notImported = files.filter((file) => !importedIds.has(file.id))
  const toCheck =
    register.imports.data?.files.reduce((sum, file) => sum + file.periods_with_checks, 0) ?? 0
  const readyToSave =
    register.imports.data?.files.reduce((sum, file) => sum + file.available_periods, 0) ?? 0
  const calls = judgements.data?.case ?? {}
  const openCalls = Number(calls.open ?? 0)
  const guesses = Number(calls.inferred ?? 0)
  const findingCount = findings.data?.total ?? findings.data?.entries.length ?? 0
  const registerReady = held(register.files) && held(register.imports)
  const registerState =
    failed(register.files) || failed(register.imports) ? "Statement status could not be loaded" : "Checking statement files…"
  const judgementsHref = (status: string, strength?: string) =>
    `/cases/${caseId}/financial?${new URLSearchParams({
      view: "statements",
      judgements: "1",
      jStatus: status,
      ...(strength ? { jStrength: strength } : {}),
    })}`
  const currency = currencies.includes(chosenCurrency) ? chosenCurrency : currencies[0] || ""
  const money = moneyBy.get(currency)
  const exact = (minor: bigint) => `${formatLedgerAmount(String(minor), currency).text} ${currency}`
  // One next step: the first unfinished thing, in the order the work runs.
  const next: { eyebrow?: string; title: string; sub: string; action: string; onClick: () => void } =
    !registerReady
      ? { title: "Your case at a glance", sub: registerState, action: "Open statements", onClick: () => navigate("statements") }
      : !files.length
        ? { title: "Start with a statement.", sub: "Upload the PDFs, check what Loupe read, then investigate.", action: "Open statement files", onClick: () => navigate("statements") }
        : toCheck
          ? { title: `${plural(toCheck, "statement needs", "statements need")} a check.`, sub: "Check them, then the ledger is complete.", action: `Check the ${plural(toCheck, "statement")} →`, onClick: () => navigate("statements") }
          : notImported.length
            ? { title: `${plural(notImported.length, "file has", "files have")} no saved statements yet.`, sub: "They may be waiting for review, still being read, or duplicates.", action: "See what needs saving →", onClick: () => navigate("statements") }
            : !totalsReady
              ? { title: "Your case at a glance", sub: totals.isError ? "Payments could not be counted. Open Transactions to try again." : "Counting payments…", action: "Open transactions", onClick: () => navigate("transactions") }
            : uncategorised
              ? { title: `${plural(uncategorised, "payment has", "payments have")} no category yet.`, sub: "Give each one a category so every total breaks down.", action: `Categorise ${n(uncategorised)} →`, onClick: () => navigate("transactions") }
              // Neither "waiting for a look" nor "checked" is known until Loupe's calls and the findings are counted.
              : !held(judgements)
                ? { title: "Your case at a glance", sub: judgements.isError ? "Loupe's calls could not be counted." : "Counting Loupe's calls…", action: "Open statements", onClick: () => navigate("statements") }
              : openCalls
                ? { title: `${plural(openCalls, "call")} Loupe made ${openCalls === 1 ? "is" : "are"} waiting for a look.`, sub: "Confirm the ones that look right, correct the rest.", action: "Spot-check Loupe →", onClick: () => go(judgementsHref("open")) }
                : !held(findings)
                  ? { title: "The ledger is checked.", sub: findings.isError ? "Findings could not be loaded." : "Loading findings…", action: "Open Findings & Observations →", onClick: () => navigate("findings") }
                : !findingCount
                  ? { title: "The ledger is checked.", sub: "Follow the money and record what needs explaining.", action: "Follow the money →", onClick: () => navigate("follow-money") }
                  : { title: "The ledger is checked.", sub: `${plural(findingCount, "finding")} saved. Keep going, or build the report.`, action: "Open Findings & Observations →", onClick: () => navigate("findings") }
  const steps: Step[] = [
    // Until the statement files and their saved readings are in, these two say so instead of counting nothing as 0.
    { name: "Load", detail: registerReady ? plural(files.length, "file") : registerState, done: registerReady && files.length > 0 },
    { name: "Read", detail: registerReady ? `${n(importedIds.size)} saved${toCheck ? ` · ${n(toCheck)} to check` : ""}${notImported.length ? ` · ${n(notImported.length)} not saved` : ""}` : registerState, done: registerReady && files.length > 0 && !toCheck && !notImported.length },
    { name: "Check", detail: held(judgements) ? (openCalls ? `${n(openCalls)} of Loupe's calls open` : "Loupe's calls checked") : "Loupe's calls", done: held(judgements) && !openCalls },
    // 07 section 8: a case with no payments (phones only, so far) says what is absent, never "0 payments"
    { name: "Analyse", detail: totalsReady ? (payments ? `${plural(payments, "payment")}${uncategorised ? ` · ${n(uncategorised)} uncategorised` : ""}` : "No payments yet") : totals.isError ? "Payments could not be counted" : "Counting payments…", done: totalsReady && payments > 0 && !uncategorised },
    { name: "Report", detail: !held(findings) ? (findings.isError ? "Findings could not be loaded" : "Loading findings…") : findingCount ? plural(findingCount, "finding") : "No findings yet", done: held(findings) && findingCount > 0 },
  ]
  const now = steps.findIndex((step) => !step.done)
  // Every count shown from an answer whose refresh failed is named here, so none of them reads as current.
  const stale = [
    { what: "statement files", queries: [register.files, register.imports] },
    { what: "Loupe's calls", queries: [judgements] },
    { what: "findings", queries: [findings] },
    { what: "payment figures", queries: [totals, panels] },
  ].filter(({ queries }) => queries.some((query) => query.isError && held(query)))
  // A failed query keeps isError while it is fetched again: the note says it is being loaded until it lands.
  const reloading = stale.some(({ queries }) => queries.some((query) => query.isFetching))
  return (
    <div className="space-y-6 bg-[#f4f3ef] p-4 sm:p-5 dark:bg-transparent">
      {stale.length > 0 && (
        <p role="alert" className="rounded border border-status-warning/50 bg-status-warning-soft px-4 py-2 text-sm text-status-warning">
          {`These could not be updated and show the last ones loaded: ${stale.map(({ what }) => what).join(", ")}.`}{" "}
          <button
            type="button"
            className="underline disabled:no-underline disabled:opacity-70"
            disabled={reloading}
            aria-busy={reloading}
            onClick={() => stale.forEach(({ queries }) => queries.forEach((query) => void query.refetch()))}
          >
            {reloading ? "Loading them again…" : "Load them again"}
          </button>
        </p>
      )}
      <section
        aria-label="Next for you"
        className="space-y-7 rounded-2xl p-5 text-[#f7f7f8] sm:p-8"
        style={{ background: "radial-gradient(1100px 420px at 90% -20%, #3a1319 0%, #0b0c0f 62%)" }}
      >
        <div className="flex flex-wrap items-stretch gap-7">
          <div className="flex min-w-0 flex-[1_1_420px] flex-col justify-center gap-3">
            <span className={`${eyebrow} text-[#e33b4c]`}>Next for you</span>
            <h2 className="text-3xl font-semibold leading-[1.05] sm:text-[42px]" style={heading}>
              {next.title}
              <br />
              <span className="text-[#9a9da5]">{next.sub}</span>
            </h2>
            <div className="mt-1 flex flex-wrap gap-2.5">
              <button
                type="button"
                onClick={next.onClick}
                className="inline-flex items-center gap-2 rounded-lg bg-[#b41624] px-[18px] py-3 text-[15px] font-semibold text-white hover:bg-[#9a121f]"
              >
                {next.action}
              </button>
              <button
                type="button"
                onClick={() => navigate("transactions")}
                className="inline-flex items-center gap-2 rounded-lg border border-[#3b3d44] px-[18px] py-3 text-[15px] font-semibold text-[#f7f7f8] hover:bg-[#202126]"
              >
                Skip to transactions
              </button>
              <button
                type="button"
                onClick={() => navigate("statements")}
                className="inline-flex items-center gap-2 rounded-lg border border-[#3b3d44] px-[18px] py-3 text-[15px] font-semibold text-[#f7f7f8] hover:bg-[#202126]"
              >
                Add or review statements
              </button>
            </div>
          </div>
          <div className="flex min-w-0 flex-[0_1_380px] flex-col gap-3 rounded-[14px] border border-[#292b32] bg-[#17181c] p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={`${eyebrow} text-[#9a9da5]`}>
                Money in this scope{currency ? ` · ${currency}` : ""}
              </span>
              {currencies.length > 1 && (
                <div role="group" aria-label="Currency" className="inline-flex rounded-lg border border-[#292b32] bg-[#0b0c0f] p-[3px]">
                  {currencies.map((code) => (
                    <button
                      key={code}
                      type="button"
                      aria-pressed={code === currency}
                      onClick={() => setChosenCurrency(code)}
                      className={`rounded-md px-2.5 py-1 text-[12px] font-semibold ${code === currency ? "bg-[#f7f7f8] text-[#0b0c0f]" : "text-[#bfc1c8] hover:text-white"}`}
                    >
                      {code} · {n(currencyCounts.get(code) ?? 0)}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {!totalsReady && !totals.isError ? (
              <p role="status" className="text-[#bfc1c8]">Adding up payments…</p>
            ) : !totalsReady ? (
              <p role="alert" className="text-[#bfc1c8]">Payments could not be added up. Open Transactions to try again.</p>
            ) : (
              <>
                <div className="flex items-baseline justify-between" title={exact(money?.credit ?? 0n)}>
                  <span className="text-[#bfc1c8]"><span aria-hidden="true">↓ </span>In</span>
                  <span className="text-3xl font-semibold tabular-nums text-[#5fd39a]" style={heading}>
                    +{compactMoney(minorToNumber(money?.credit ?? 0n, currency))}
                  </span>
                </div>
                <div className="flex items-baseline justify-between" title={exact(money?.debit ?? 0n)}>
                  <span className="text-[#bfc1c8]"><span aria-hidden="true">↑ </span>Out</span>
                  <span className="text-3xl font-semibold tabular-nums" style={heading}>
                    −{compactMoney(minorToNumber(money?.debit ?? 0n, currency))}
                  </span>
                </div>
                <div className="h-px bg-[#292b32]" />
                <div className="flex flex-wrap items-baseline justify-between gap-2 text-[14px]">
                  <span className="text-[#bfc1c8]">{plural(accountCount, "account")} · {span}</span>
                  <button type="button" onClick={() => navigate("transactions")} className="font-semibold text-[#f7f7f8] hover:underline">
                    Open →
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
        <ol aria-label="Your progress on this case" className="grid grid-cols-2 gap-3 sm:grid-cols-5 sm:gap-2">
          {steps.map((step, index) => {
            const state = step.done ? "done" : index === now ? "now" : "todo"
            return (
              <li key={step.name} className="flex flex-col gap-2" aria-current={state === "now" ? "step" : undefined}>
                <span
                  aria-hidden="true"
                  className="h-[5px] rounded-[3px]"
                  style={{ background: state === "done" ? "#2fae6c" : state === "now" ? "#e33b4c" : "#292b32" }}
                />
                <span className="flex items-center gap-2">
                  <span
                    className="inline-flex size-6 items-center justify-center rounded-full text-[12px] font-semibold"
                    style={
                      state === "done"
                        ? { background: "#2fae6c", color: "#0b0c0f" }
                        : state === "now"
                          ? { background: "#e33b4c", color: "#fff", boxShadow: "0 0 0 5px rgba(227,59,76,.18)" }
                          : { background: "#202126", color: "#9a9da5", border: "1px solid #3b3d44" }
                    }
                  >
                    {state === "done" ? "✓" : index + 1}
                  </span>
                  <span className={`text-base font-semibold ${state === "todo" ? "text-[#9a9da5]" : "text-[#f7f7f8]"}`} style={heading}>
                    {step.name}
                  </span>
                  <span className="sr-only">{state === "done" ? "(done)" : state === "now" ? "(now)" : "(to do)"}</span>
                </span>
                <span className="pl-8 text-[13px] text-[#9a9da5]">{step.detail}</span>
              </li>
            )
          })}
        </ol>
      </section>
      <WorkspaceScope caseId={caseId} />
      <section aria-label="Jump in" className="space-y-3">
        <h2 className="text-[26px] font-semibold" style={heading}>Jump in</h2>
        <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
          <button type="button" onClick={() => navigate("follow-money")} className="flex min-h-[170px] flex-col gap-3 rounded-[14px] bg-[#3a6fd8] p-5 text-left text-white transition-transform hover:-translate-y-[3px]">
            <span className={`${eyebrow} text-[#dbe6ff]`}>Follow the money</span>
            <span className="text-[22px] font-semibold leading-tight" style={heading}>Where did the money go?</span>
            <span className="mt-auto text-sm text-[#dbe6ff]">Trace a payment across accounts →</span>
          </button>
          <button
            type="button"
            onClick={() => navigate("transactions")}
            className={`flex min-h-[170px] flex-col gap-3 rounded-[14px] p-5 text-left transition-transform hover:-translate-y-[3px] ${!totalsReady ? "bg-[#ecebe6] text-[#3b3d44]" : uncategorised ? "border-2 border-dashed border-[#d99a2b] bg-[#fdf0d5] text-[#5c3800]" : "bg-[#e4f4e9] text-[#1d6a3a]"}`}
          >
            <span className={`${eyebrow} ${!totalsReady ? "text-[#3b3d44]" : uncategorised ? "text-[#8a5300]" : "text-[#1d6a3a]"}`}>Categorise</span>
            <span className="text-[22px] font-semibold leading-tight tabular-nums" style={heading}>
              {!totalsReady ? (totals.isError ? "Payments could not be counted" : "Counting payments…") : uncategorised ? `${plural(uncategorised, "payment has", "payments have")} no category yet` : payments ? "Every payment has a category" : "No payments to categorise yet"}
            </span>
            <span className="mt-auto text-sm">{totalsReady && uncategorised ? "Categorise them in bulk →" : "See where the money went →"}</span>
          </button>
          <button type="button" onClick={() => go(judgementsHref(openCalls ? "open" : "all", openCalls && guesses ? "inferred" : undefined))} className="flex min-h-[170px] flex-col gap-3 rounded-[14px] bg-[#0f8a7e] p-5 text-left text-white transition-transform hover:-translate-y-[3px]">
            <span className={`${eyebrow} text-[#c9efe9]`}>Spot-check Loupe</span>
            <span className="text-[22px] font-semibold leading-tight tabular-nums" style={heading}>
              {held(judgements) ? `${plural(Number(calls.total ?? 0), "call")} Loupe made for you` : judgements.isError ? "Loupe's calls could not be counted" : "Counting Loupe's calls…"}
            </span>
            <span className="mt-auto text-sm text-[#c9efe9]">
              {openCalls ? `${n(openCalls)} open${guesses ? ` · start with the ${n(guesses)} guesses` : ""} →` : "See them all →"}
            </span>
          </button>
          <button type="button" onClick={() => navigate("findings")} className="flex min-h-[170px] flex-col gap-3 rounded-[14px] bg-[#14161b] p-5 text-left text-white transition-transform hover:-translate-y-[3px]">
            <span className={`${eyebrow} text-[#9a9da5]`}>Findings</span>
            <span className="text-[22px] font-semibold leading-tight" style={heading}>Turn what you find into a report</span>
            <span className="mt-auto text-sm text-[#bfc1c8]">{held(findings) ? `${plural(findingCount, "finding")} so far →` : "Open Findings & Observations →"}</span>
          </button>
        </div>
      </section>
      {!held(panels) && !panels.isError ? (
        <p role="status" className="p-6">
          Loading this case’s payments
          {totalsReady ? ` (${plural(payments, "payment")})` : ""}…
        </p>
      ) : !panels.data || !panels.data.complete || !panelTotals ? (
        <div role="alert" className="rounded border p-4 space-y-2">
          <p>
            {!panels.data
              ? panels.error?.message
              : "Not all payments were returned. These views cannot yet describe the whole selection."}
          </p>
          <Button onClick={() => void panels.refetch()}>
            Load payments again
          </Button>
        </div>
      ) : (<>
        {(panels.isFetching || totals.isFetching) && (
          <p role="status" className="text-sm text-muted-foreground">
            Updating these figures…
          </p>
        )}
        <PaymentTotalsView
          payments={panels.data.totals.payments}
          inventory={panelTotals.inventory}
          totals={panelTotals.totals}
          unreadable={panels.data.totals.unreadable}
          label="Imported payments in the selected accounts and dates"
        />
        <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
          <div className="min-w-0 space-y-5">
            {panels.data.connections.payments ? (
              <MoneyConnectionsView
                payments={panels.data.connections.payments}
                groups={panels.data.connections.groups}
                onOpen={(figure, title) => openFigure(figure, title, drawnCount(panels.data!.connections.groups, figure))}
              />
            ) : (
              <section className="space-y-3 rounded-[14px] bg-card p-6" style={card}>
                <Files className="text-primary" />
                <h3 className="text-lg font-semibold">
                  Start with a statement
                </h3>
                <p className="text-sm text-muted-foreground">
                  Open the file register, upload your PDFs and review their
                  extracted payments against the originals. Confirm each import
                  once, then return here to investigate.
                </p>
                <Button onClick={() => navigate("statements")}>
                  Open statement files
                </Button>
              </section>
            )}
            {!!comparisons?.pairs && (
              <section
                className="space-y-3 rounded-[14px] bg-card p-5"
                style={card}
              >
                <p className={`${eyebrow} text-[#1d4aa6] dark:text-[#9bb8f0]`}>
                  Money in, then money out
                </p>
                <h3 className="text-xl font-semibold" style={heading}>
                  {comparisons.pairs} times money arrived and the next payment
                  left within a week
                </h3>
                <p className="text-sm text-muted-foreground">
                  A starting point for review, not proof one funded the other.
                  <InfoTip text="For each example, Loupe found money coming into an account, followed by its next recorded payment out within seven days. This is a starting point for review, not evidence of suspicious activity or proof that the incoming money funded the payment." />
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() =>
                      openFigure(
                        { list: "comparisons" },
                        "Receipts and subsequent payments",
                        comparisons.count
                      )
                    }
                  >
                    View these payments
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => navigate("follow-money")}
                  >
                    Compare incoming and outgoing payments{" "}
                    <ArrowRight size={15} />
                  </Button>
                </div>
              </section>
            )}
            <section
              className="space-y-3 rounded-[14px] bg-card p-5"
              style={card}
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-lg font-semibold" style={heading}>
                  Saved investigation work
                </h3>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate("findings")}
                >
                  Open Findings &amp; Observations
                </Button>
              </div>
              {!held(findings) && !findings.isError ? (
                <p role="status">Loading findings…</p>
              ) : !held(findings) ? (
                <p role="alert">
                  Saved findings could not be loaded. Open Findings &amp;
                  Observations to try again.
                </p>
              ) : findings.data?.entries.length ? (
                <ul className="divide-y">
                  {findings.data.entries.map((entry) => (
                    <li key={entry.id} className="py-3">
                      <a
                        className="font-medium text-sm hover:underline"
                        href={`/cases/${caseId}/workspace?view=casework&entry=${entry.id}`}
                      >
                        {entry.title || "Untitled note"}
                      </a>
                      <p className="text-xs text-muted-foreground">
                        {entry.author_name ||
                          entry.author_email ||
                          "Author not recorded"}
                        {entry.updated_at
                          ? ` · ${new Date(entry.updated_at).toLocaleDateString()}`
                          : ""}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    No findings saved yet.
                    <InfoTip text="Write a question to follow up, or select payments and record what you noticed with the evidence attached." />
                  </p>
                  {canEdit && (
                    <Button variant="outline" onClick={() => setFinding(true)}>
                      Create observation
                    </Button>
                  )}
                </>
              )}
            </section>
          </div>
          <aside className="space-y-4">
            <section
              className="space-y-4 rounded-[14px] bg-card p-5"
              style={card}
            >
              <div className="flex gap-2 items-center">
                <BookOpenCheck size={19} className="text-[#c67a10]" />
                <h3 className="font-semibold" style={heading}>
                  Your statements
                  <InfoTip text="These file counts cover the whole case. Saved statements are available for investigation, including statements with no transactions. Files not yet saved may be waiting for review, still being read, or duplicate copies. One file can contain several statements." />
                </h3>
              </div>
              {failed(register.files) || failed(register.imports) ? (
                <p role="alert" className="text-sm">
                  Statement status could not be loaded. Open the file register
                  to try again.
                </p>
              ) : !registerReady ? (
                <p role="status">Checking statement files…</p>
              ) : (
                <>
                  <dl className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <dt>Files added for financial review</dt>
                      <dd className="font-semibold">{files.length}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Files with saved statements</dt>
                      <dd className="font-semibold">{importedIds.size}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Files with no saved statements yet</dt>
                      <dd className={`rounded-md px-2 font-semibold tabular-nums ${notImported.length ? "bg-[#fdf0d5] text-[#8a5300]" : ""}`}>{notImported.length}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt>Statements ready to save together</dt>
                      <dd className={`rounded-md px-2 font-semibold tabular-nums ${readyToSave ? "bg-[#e6efff] text-[#1f4fa8]" : ""}`}>{readyToSave}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt>Statements needing a check</dt>
                      <dd className={`rounded-md px-2 font-semibold tabular-nums ${toCheck ? "bg-[#fdf0d5] text-[#8a5300]" : ""}`}>{toCheck}</dd>
                    </div>
                  </dl>
                  {register.imports.data?.truncated && (
                    <p role="alert" className="text-sm">
                      Import status is incomplete. Check each file for its full
                      record.
                    </p>
                  )}
                </>
              )}
              {totalsReady && unknownDates > 0 && (
                <p className="text-sm">
                  {unknownDates} payments have only a statement end date. Check
                  their original records before comparing timing.
                </p>
              )}
              <Button
                className="w-full"
                variant="outline"
                onClick={() => navigate("statements")}
              >
                See what needs saving
              </Button>
            </section>
            <section
              className="space-y-3 rounded-[14px] bg-card p-5"
              style={card}
            >
              <WalletCards size={20} className="text-[#c67a10]" />
              <h3 className="font-semibold" style={heading}>
                {totalsReady
                  ? `${accountCount} accounts with payments in this scope`
                  : totals.isError
                    ? "Accounts with payments in this scope could not be counted"
                    : "Counting accounts with payments in this scope…"}
              </h3>
              <p className="text-sm text-muted-foreground">
                Holders, periods and coverage in Statements & accounts.
              </p>
              <Button variant="outline" onClick={() => navigate("statements")}>
                Review accounts and coverage
              </Button>
            </section>
            <section
              className="space-y-3 rounded-[14px] bg-card p-5"
              style={card}
            >
              <h3 className="font-semibold" style={heading}>
                Explore activity over time
                <InfoTip text="Compare periods, open the entries behind a change and save your explanation." />
              </h3>
              <Button variant="outline" onClick={() => navigate("trends")}>
                Open Trends
              </Button>
            </section>
          </aside>
        </div>
      </>)}
      <OverviewStatementCoverage caseId={caseId} active={active} />
      {opening && (
        <div
          role={opening.error ? "alert" : "status"}
          className="fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-lg border bg-card p-3 text-sm shadow"
        >
          {opening.error ? (
            <>
              <span>
                The payments behind “{opening.title}” could not be read: {opening.error}.
              </span>
              <Button size="sm" variant="outline" onClick={() => openFigure(opening.figure, opening.title, opening.drawn)}>
                Try again
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  openingNow.current = null
                  setOpening(null)
                }}
              >
                Close
              </Button>
            </>
          ) : (
            <span>Reading the {opening.drawn.toLocaleString("en-US")} payments behind “{opening.title}”…</span>
          )}
        </div>
      )}
      {open && (
        <PaymentComparison
          caseId={caseId}
          ids={open.ids}
          title={open.title}
          onClose={() => setOpen(null)}
        />
      )}
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          onClose={() => setFinding(false)}
        />
      )}
    </div>
  )
}
