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
  // Dark Loupe bar: the white pill marks where you are; a More destination joins the bar while open.
  const trigger =
    "h-9 flex-none rounded-md px-3 text-[14px] font-medium text-[#bfc1c8] hover:bg-[#202126] hover:text-white data-[state=active]:!bg-[#25272d] data-[state=active]:!text-white dark:text-[#bfc1c8] after:hidden focus-visible:ring-[#e33b4c]/60"
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2 bg-[#0b0c0f] px-3 pb-2 pt-1.5 text-[#f7f7f8]">
      <TabsList
        variant="line"
        aria-label="Financial"
        className="group-data-[orientation=horizontal]/tabs:h-auto min-h-10 flex-wrap justify-start gap-0.5"
      >
        {primary.map(([key, label]) => (
          <TabsTrigger key={key} value={key} className={trigger}>
            {label}
          </TabsTrigger>
        ))}
        {extra && (
          <>
            <span aria-hidden="true" className="mx-1 h-5 w-px bg-[#3a3d45]" />
            <TabsTrigger value={extra[0]} className={`${trigger} data-[state=active]:!shadow-[inset_0_-2px_0_#e33b4c]`}>
              {extra[1]}
            </TabsTrigger>
          </>
        )}
      </TabsList>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="inline-flex h-9 items-center gap-1 rounded-md px-3 text-[14px] font-medium text-[#bfc1c8] hover:bg-[#202126] hover:text-white data-[state=open]:bg-[#25272d] data-[state=open]:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#e33b4c]/60"
          >
            More financial tools ({analysis.length + history.length})
            <span aria-hidden="true">▾</span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-64">
          <DropdownMenuLabel className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Further analysis</DropdownMenuLabel>
          {analysis.map(([key, label]) => (
            <DropdownMenuItem key={key} onSelect={() => onChange(key)} className={key === value ? "font-semibold" : undefined}>
              {label}
              {key === value && <span className="ml-auto text-xs text-muted-foreground">open</span>}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Import and review history</DropdownMenuLabel>
          {history.map(([key, label]) => (
            <DropdownMenuItem key={key} onSelect={() => onChange(key)} className={key === value ? "font-semibold" : undefined}>
              {label}
              {key === value && <span className="ml-auto text-xs text-muted-foreground">open</span>}
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
