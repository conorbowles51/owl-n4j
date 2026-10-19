import { Fragment } from "react"
import { useParams } from "react-router-dom"
import { resetFinancialView } from "../lib/reset-financial-view"
import { toast } from "sonner"
import { useEffect, useState, type ReactNode, type ComponentProps } from "react"
import { TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import type { FinancialMainView } from "../stores/financial.store"

const primary: [FinancialMainView, string][] = [
  ["overview", "Overview"],
  ["statements", "Statements & accounts"],
  ["transactions", "Transactions"],
  ["counterparties", "People & businesses"],
  ["follow-money", "Follow money"],
  ["trends", "Trends"],
  ["findings", "Findings & Observations"],
]
const analysis: [FinancialMainView, string][] = [
  ["transfers", "Compare transfers"],
  ["patterns", "Look for patterns"],
  ["posting-graph", "Payment graph"],
  ["tracing", "Trace funds"],
  ["case-context", "Payments and case events"],
]
const history: [FinancialMainView, string][] = [
  ["ledger", "Import review"],
  ["quarantine", "Excluded transactions"],
  ["runs", "Processing history"],
  ["decisions", "Change history"],
]
export function FinancialNavigation({
  value,
  onChange,
}: {
  value: FinancialMainView
  onChange: (value: FinancialMainView) => void
}) {
  const extra = [...analysis, ...history].find(([key]) => key === value)
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-card px-3">
      <TabsList
        variant="line"
        className="group-data-[orientation=horizontal]/tabs:h-auto min-h-10 flex-wrap justify-start"
      >
        {primary.map(([key, label]) => (
          <TabsTrigger key={key} value={key} className="h-10">
            {label}
          </TabsTrigger>
        ))}
        {extra && (
          <TabsTrigger value={extra[0]} className="h-10">
            {extra[1]}
          </TabsTrigger>
        )}
      </TabsList>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm">
            More financial tools
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Further analysis</DropdownMenuLabel>
          {analysis.map(([key, label]) => (
            <DropdownMenuItem key={key} onSelect={() => onChange(key)}>
              {label}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Import and review history</DropdownMenuLabel>
          {history.map(([key, label]) => (
            <DropdownMenuItem key={key} onSelect={() => onChange(key)}>
              {label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

// Open a tool on first use, then keep its working form and results during tab changes.
export function RetainedFinancialTab({
  active,
  children,
  onReset,
  ...props
}: ComponentProps<typeof TabsContent> & {
  active: boolean
  onReset?: () => void
}) {
  const { caseId: routeCaseId, id } = useParams()
  const caseId = routeCaseId ?? id
  const [resetVersion, setResetVersion] = useState(0)
  const [opened, setOpened] = useState(active)
  useEffect(() => {
    if (active) setOpened(true)
  }, [active])
  return (
    <TabsContent
      {...props}
      forceMount={active || opened ? true : undefined}
      style={!active ? { display: "none" } : undefined}
    >
      <div className="flex shrink-0 justify-end border-b bg-background px-4 py-1">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          title="Reset this tab’s filters and layout. Saved casework stays unchanged."
          onClick={() => {
            if (caseId) resetFinancialView(caseId, props.value)
            onReset?.()
            setResetVersion((version) => version + 1)
            toast.success("View reset. Saved casework is unchanged.")
          }}
        >
          Reset view
        </Button>
      </div>
      <Fragment key={resetVersion}>{children}</Fragment>
    </TabsContent>
  )
}

export function RetainedFinancialTool({
  active,
  children,
}: {
  active: boolean
  children: ReactNode
}) {
  const [opened, setOpened] = useState(active)
  useEffect(() => {
    if (active) setOpened(true)
  }, [active])
  return (
    <div style={active ? undefined : { display: "none" }}>
      {active || opened ? children : null}
    </div>
  )
}
