import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { aiCaseLimitAPI, aiCostsAPI } from "@/features/admin/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value)
}

function limitOf(text: string) {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  return Number.isFinite(value) && value >= 0 ? value : undefined
}

/** The saved AI spending limits, spend beside them, and the alerts. Empty means no cap, and it says so. */
export function AIBudgetCard() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ["admin", "ai-budget"], queryFn: () => aiCostsAPI.getBudget() })
  const [caseText, setCaseText] = useState<string | null>(null)
  const [monthText, setMonthText] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (limits: { case_limit_usd: number | null; month_limit_usd: number | null }) =>
      aiCostsAPI.saveBudget(limits),
    onSuccess: (budget) => {
      queryClient.setQueryData(["admin", "ai-budget"], budget)
      setCaseText(null)
      setMonthText(null)
    },
  })
  const [pickedCase, setPickedCase] = useState("")
  const [pickedText, setPickedText] = useState("")
  const saveCase = useMutation({
    mutationFn: (args: { caseId: string; limit: number | null }) => aiCaseLimitAPI.save(args.caseId, args.limit),
    onSuccess: (budget) => {
      queryClient.setQueryData(["admin", "ai-budget"], budget)
      setPickedText("")
    },
  })
  const budget = query.data
  if (query.isError) {
    return (
      <Card>
        <CardContent className="py-3 text-sm text-destructive">
          The AI spending limits could not be read, so what is in force is not shown here.
        </CardContent>
      </Card>
    )
  }
  if (!budget) return null
  const caseValue = caseText ?? (budget.case_limit_usd?.toString() || "")
  const monthValue = monthText ?? (budget.month_limit_usd?.toString() || "")
  const caseLimit = limitOf(caseValue)
  const monthLimit = limitOf(monthValue)
  const atRisk = budget.cases.filter((row) => (row.percent ?? 0) >= 80)
  return (
    <Card data-testid="ai-budget">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">AI spending limits</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {budget.capped ? (
          <p>
            At a limit, new AI runs are refused with the reason. Work already started finishes, and a batch waits after
            its current file. Nothing is dropped.
          </p>
        ) : (
          <p data-testid="ai-budget-no-cap">No limit is set, so AI spending has no cap.</p>
        )}
        <p className="text-muted-foreground">
          {budget.month}: {money(budget.month_spent_usd)} spent
          {budget.month_limit_usd !== null
            ? ` of ${money(budget.month_limit_usd)} (${budget.month_percent} %)`
            : ""}
          .
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-xs">
            <span>Limit per case (USD)</span>
            <Input
              inputMode="decimal"
              aria-label="Limit per case in dollars"
              placeholder="No limit"
              value={caseValue}
              onChange={(event) => setCaseText(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span>Limit per calendar month (USD)</span>
            <Input
              inputMode="decimal"
              aria-label="Limit per month in dollars"
              placeholder="No limit"
              value={monthValue}
              onChange={(event) => setMonthText(event.target.value)}
            />
          </label>
          <Button
            size="sm"
            disabled={save.isPending || caseLimit === undefined || monthLimit === undefined}
            onClick={() =>
              save.mutate({ case_limit_usd: caseLimit ?? null, month_limit_usd: monthLimit ?? null })
            }
          >
            Save limits
          </Button>
        </div>
        {(caseLimit === undefined || monthLimit === undefined) && (
          <p className="text-xs text-destructive">A limit is a number of dollars, or empty for no limit.</p>
        )}
        {save.isError && <p className="text-xs text-destructive">The limits were not saved. Try again.</p>}
        {atRisk.length > 0 && (
          <ul className="space-y-1" aria-label="Cases at 80 % or more of their limit">
            {atRisk.map((row) => (
              <li key={row.case_id}>
                {row.title}: {money(row.spent_usd)} of {money(row.limit_usd ?? 0)} ({row.percent} %)
              </li>
            ))}
          </ul>
        )}
        <div className="space-y-2 border-t pt-3" data-testid="ai-case-limits">
          <p className="text-xs">
            A case's own limit replaces the limit per case, higher or lower. Clear it to return the case to the limit
            per case.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="space-y-1 text-xs">
              <span>Case</span>
              <select
                aria-label="Case for its own limit"
                className="block h-9 rounded-md border bg-background px-2 text-sm"
                value={pickedCase}
                onChange={(event) => {
                  setPickedCase(event.target.value)
                  const own = budget.case_limits?.[event.target.value.toLowerCase()]
                  setPickedText(own === undefined ? "" : String(own))
                }}
              >
                <option value="">Choose a case</option>
                {budget.case_choices.map((choice) => (
                  <option key={choice.id} value={choice.id}>
                    {choice.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-xs">
              <span>Its own limit (USD)</span>
              <Input
                inputMode="decimal"
                aria-label="Own limit for the chosen case in dollars"
                placeholder="Default"
                value={pickedText}
                onChange={(event) => setPickedText(event.target.value)}
              />
            </label>
            <Button
              size="sm"
              disabled={saveCase.isPending || !pickedCase || !pickedText.trim() || limitOf(pickedText) === undefined}
              onClick={() => saveCase.mutate({ caseId: pickedCase, limit: limitOf(pickedText) ?? null })}
            >
              Set case limit
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={saveCase.isPending || !pickedCase || budget.case_limits?.[pickedCase.toLowerCase()] === undefined}
              onClick={() => saveCase.mutate({ caseId: pickedCase, limit: null })}
            >
              Clear case limit
            </Button>
          </div>
          {saveCase.isError && <p className="text-xs text-destructive">The case limit was not saved. Try again.</p>}
          {budget.cases.length > 0 && (
            <ul className="space-y-1 text-xs" aria-label="Cases, their spend and limit">
              {budget.cases.map((row) => (
                <li key={row.case_id}>
                  {row.title}: {money(row.spent_usd)} spent;{" "}
                  {row.limit_usd === null
                    ? "no limit"
                    : `limit ${money(row.limit_usd)} (${row.own_limit ? "its own" : "the default"})`}
                </li>
              ))}
            </ul>
          )}
        </div>
        {budget.alerts.length > 0 && (
          <ul className="space-y-1 text-xs text-muted-foreground" aria-label="Spending alerts">
            {budget.alerts.map((alert) => (
              <li key={alert.key}>
                {alert.at.slice(0, 10)}: {alert.message}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
