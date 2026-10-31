import { useState } from "react"
import { Play, Clock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CypherInput } from "@/components/ui/cypher-input"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { graphAPI } from "../api"

interface CypherPanelProps {
  caseId: string
  className?: string
}

interface QueryResult {
  columns: string[]
  rows: Record<string, unknown>[]
  rowLimit: number
  truncated: boolean
}



interface HistoryEntry {
  query: string
  timestamp: Date
  rowCount: number
}

export function CypherPanel({ caseId, className }: CypherPanelProps) {
  const [query, setQuery] = useState("")
  const [result, setResult] = useState<QueryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)

  const executeQuery = async (q: string) => {
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await graphAPI.runCaseQuery(caseId, q)
      if (!data.success) {
        setError(data.error ?? "Query failed")
        setResult(null)
        return
      }
      setResult({
        columns: data.columns,
        rows: data.results,
        rowLimit: data.row_limit,
        truncated: data.truncated,
      })
      setHistory((prev) => [
        { query: q, timestamp: new Date(), rowCount: data.results.length },
        ...prev.slice(0, 19),
      ])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed")
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const columns: DataTableColumn<Record<string, unknown>>[] =
    result?.columns.map((col) => ({
      key: col,
      header: col,
      cell: (row) => {
        const val = row[col]
        if (val === null || val === undefined) return "\u2014"
        if (typeof val === "object") return JSON.stringify(val)
        return String(val)
      },
    })) ?? []

  return (
    <div className={className}>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Cypher Query</h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowHistory(!showHistory)}
          >
            <Clock className="size-3.5" />
            History ({history.length})
          </Button>
        </div>

        <CypherInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onExecute={executeQuery}
          placeholder="MATCH (n {case_id: $case_id}) RETURN n.name, labels(n) LIMIT 25"
        />
        <p className="text-[11px] text-muted-foreground">
          Read only, within this case: bind every node and relationship to the case with{" "}
          <code>{"{case_id: $case_id}"}</code>.
        </p>

        <div className="flex gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => executeQuery(query)}
            disabled={loading || !query.trim()}
          >
            {loading ? <LoadingSpinner size="sm" /> : <Play className="size-3.5" />}
            Execute
          </Button>
        </div>
      </div>

      {/* History dropdown */}
      {showHistory && history.length > 0 && (
        <>
          <Separator className="my-3" />
          <ScrollArea className="max-h-[150px]">
            <div className="space-y-1">
              {history.map((entry, i) => (
                <button
                  key={i}
                  className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left hover:bg-muted/50"
                  onClick={() => {
                    setQuery(entry.query)
                    setShowHistory(false)
                  }}
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">
                    {entry.query}
                  </span>
                  <Badge variant="slate" className="shrink-0 text-[10px]">
                    {entry.rowCount} rows
                  </Badge>
                </button>
              ))}
            </div>
          </ScrollArea>
        </>
      )}

      <Separator className="my-3" />

      {/* Results */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-500/10 p-3 text-xs text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner />
        </div>
      )}

      {result && !loading && (
        <div>
          <div className="mb-2 flex items-center justify-between">
            <Badge variant="slate">{result.rows.length} results</Badge>
          </div>
          {result.truncated && (
            <p role="status" className="mb-2 rounded-md bg-amber-50 p-2 text-xs text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
              Showing the first {result.rowLimit} rows only: the query returned more. Add a LIMIT or narrow it.
            </p>
          )}
          {result.rows.length === 0 ? (
            <EmptyState title="No results" description="Query returned no data" className="py-6" />
          ) : (
            <DataTable
              columns={columns}
              data={result.rows}
              getRowKey={(row) => JSON.stringify(row)}
            />
          )}
        </div>
      )}
    </div>
  )
}
