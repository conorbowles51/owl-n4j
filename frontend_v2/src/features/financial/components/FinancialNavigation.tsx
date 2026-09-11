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
  ["transactions", "Transactions"],
  ["statements", "Statements"],
  ["findings", "Findings"],
  ["counterparties", "People and businesses"],
  ["transfers", "Transfers"],
  ["patterns", "Patterns"],
  ["trends", "Trends"],
]
const analysis: [FinancialMainView, string][] = [
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
    <div className="flex flex-wrap items-center gap-2 border-b bg-card px-3">
      <TabsList
        variant="line"
        className="h-auto min-h-10 flex-wrap justify-start"
      >
        {primary.map(([key, label]) => (
          <TabsTrigger key={key} value={key} className="min-h-10">
            {label}
          </TabsTrigger>
        ))}
        {extra && (
          <TabsTrigger value={extra[0]} className="min-h-10">
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
  ...props
}: ComponentProps<typeof TabsContent> & { active: boolean }) {
  const [opened, setOpened] = useState(active)
  useEffect(() => {
    if (active) setOpened(true)
  }, [active])
  return (
    <TabsContent
      {...props}
      forceMount={active || opened ? true : undefined}
      style={!active ? { display: "none" } : undefined}
    />
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
