import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Bot, DollarSign, Filter, MessageSquare, RefreshCw } from "lucide-react"

import { aiCostsAPI } from "@/features/admin/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CostBadge } from "@/components/ui/cost-badge"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function chartCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value)
}

export function AICostsPage() {
  const [source, setSource] = useState("all")
  const [userId, setUserId] = useState("all")
  const [caseId, setCaseId] = useState("all")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [page, setPage] = useState(1)

  const filters = {
    source,
    user_id: userId,
    case_id: caseId,
    start_date: startDate,
    end_date: endDate,
  }

  const filtersQuery = useQuery({
    queryKey: ["admin", "ai-costs", "filters", source, startDate, endDate],
    queryFn: () =>
      aiCostsAPI.getFilters({
        source,
        start_date: startDate,
        end_date: endDate,
      }),
  })

  const summaryQuery = useQuery({
    queryKey: ["admin", "ai-costs", "summary", filters],
    queryFn: () => aiCostsAPI.getSummary(filters),
  })

  const timeseriesQuery = useQuery({
    queryKey: ["admin", "ai-costs", "timeseries", filters],
    queryFn: () => aiCostsAPI.getTimeseries(filters),
  })

  const recordsQuery = useQuery({
    queryKey: ["admin", "ai-costs", "records", filters, page],
    queryFn: () => aiCostsAPI.getRecords({ ...filters, page, page_size: 50 }),
  })

  const isLoading =
    filtersQuery.isLoading ||
    summaryQuery.isLoading ||
    timeseriesQuery.isLoading ||
    recordsQuery.isLoading

  const filtersData = filtersQuery.data
  const summary = summaryQuery.data
  const timeseries = timeseriesQuery.data?.points ?? []
  const records = recordsQuery.data?.records ?? []
  const totalCount = recordsQuery.data?.total_count ?? 0
  const totalPages = Math.max(1, Math.ceil(totalCount / 50))

  const comparisonData =
    (summary?.top_users.length ?? 0) >= 2
      ? summary?.top_users ?? []
      : summary?.top_models ?? []
  const comparisonTitle =
    (summary?.top_users.length ?? 0) >= 2 ? "Top Spenders" : "Top Models"

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-lg font-semibold">AI Costs</h1>
          <p className="text-sm text-muted-foreground">
            Track ingestion and chat spend across users and cases.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              summaryQuery.refetch()
              timeseriesQuery.refetch()
              recordsQuery.refetch()
              filtersQuery.refetch()
            }}
          >
            <RefreshCw className="mr-2 size-4" />
            Refresh
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Filter className="size-4 text-amber-500" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Select
            value={source}
            onValueChange={(value) => {
              setSource(value)
              setPage(1)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Source" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              <SelectItem value="ingestion">Ingestion</SelectItem>
              <SelectItem value="chat">Chat</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={userId}
            onValueChange={(value) => {
              setUserId(value)
              setPage(1)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="User" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Users</SelectItem>
              {filtersData?.users.map((user) => (
                <SelectItem key={user.id} value={user.id}>
                  {user.name || user.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={caseId}
            onValueChange={(value) => {
              setCaseId(value)
              setPage(1)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Case" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Cases</SelectItem>
              {filtersData?.cases.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="md:col-span-2 xl:col-span-1">
            <p className="mb-1 text-xs font-medium text-muted-foreground">Date Range</p>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                type="date"
                aria-label="Start date"
                value={startDate}
                onChange={(event) => {
                  setStartDate(event.target.value)
                  setPage(1)
                }}
              />

              <Input
                type="date"
                aria-label="End date"
                value={endDate}
                onChange={(event) => {
                  setEndDate(event.target.value)
                  setPage(1)
                }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading && !summary ? (
        <div className="flex flex-1 items-center justify-center">
          <LoadingSpinner size="lg" />
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-xs text-muted-foreground">
                  <DollarSign className="size-4 text-amber-500" />
                  Total Spend
                </CardTitle>
              </CardHeader>
              <CardContent>
                <CostBadge amount={summary?.total_cost_usd ?? 0} className="text-sm" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Bot className="size-4 text-blue-500" />
                  Ingestion
                </CardTitle>
              </CardHeader>
              <CardContent>
                <CostBadge amount={summary?.ingestion_cost_usd ?? 0} className="text-sm" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-xs text-muted-foreground">
                  <MessageSquare className="size-4 text-emerald-500" />
                  Chat
                </CardTitle>
              </CardHeader>
              <CardContent>
                <CostBadge amount={summary?.chat_cost_usd ?? 0} className="text-sm" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs text-muted-foreground">
                  Billable Calls
                </CardTitle>
              </CardHeader>
              <CardContent>
                <span className="text-2xl font-semibold">
                  {(summary?.billable_calls ?? 0).toLocaleString()}
                </span>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Spend Over Time</CardTitle>
              </CardHeader>
              <CardContent className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={timeseries}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                    <XAxis dataKey="bucket_date" tick={{ fontSize: 12 }} />
                    <YAxis tickFormatter={chartCurrency} tick={{ fontSize: 12 }} />
                    <RechartsTooltip formatter={(value: number) => chartCurrency(value)} />
                    <Area
                      type="monotone"
                      dataKey="ingestion_cost_usd"
                      stackId="cost"
                      stroke="#d97706"
                      fill="#f59e0b"
                      fillOpacity={0.8}
                      name="Ingestion"
                    />
                    <Area
                      type="monotone"
                      dataKey="chat_cost_usd"
                      stackId="cost"
                      stroke="#2563eb"
                      fill="#60a5fa"
                      fillOpacity={0.8}
                      name="Chat"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">{comparisonTitle}</CardTitle>
              </CardHeader>
              <CardContent className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={comparisonData}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 11 }}
                      interval={0}
                      angle={-15}
                      textAnchor="end"
                      height={60}
                    />
                    <YAxis tickFormatter={chartCurrency} tick={{ fontSize: 12 }} />
                    <RechartsTooltip formatter={(value: number) => chartCurrency(value)} />
                    <Bar dataKey="cost_usd" fill="#111827" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <Card className="flex flex-1 flex-col">
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <div>
                <CardTitle className="text-sm">Ledger</CardTitle>
                <p className="text-xs text-muted-foreground">
                  {totalCount.toLocaleString()} records
                </p>
              </div>
              <CostBadge amount={recordsQuery.data?.total_cost_usd ?? 0} />
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-4">
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>When</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Operation</TableHead>
                      <TableHead>User</TableHead>
                      <TableHead>Case</TableHead>
                      <TableHead>Reference</TableHead>
                      <TableHead>Model</TableHead>
                      <TableHead>Tokens</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {records.map((record) => (
                      <TableRow key={record.id}>
                        <TableCell className="text-xs text-muted-foreground">
                          {new Date(record.created_at).toLocaleString()}
                        </TableCell>
                        <TableCell>{record.source}</TableCell>
                        <TableCell>{record.operation_kind?.replaceAll("_", " ") ?? "Unknown"}</TableCell>
                        <TableCell className="whitespace-normal">
                          <div className="max-w-48">
                            <div>{record.user_name || "Unknown/System"}</div>
                            {record.user_email && (
                              <div className="text-xs text-muted-foreground">{record.user_email}</div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="whitespace-normal">
                          <div className="max-w-48">{record.case_title || "No case"}</div>
                        </TableCell>
                        <TableCell className="whitespace-normal">
                          <div className="max-w-56 text-xs text-muted-foreground">
                            {record.evidence_file_name ||
                              (record.conversation_id ? `Conversation ${record.conversation_id.slice(0, 8)}` : "—")}
                          </div>
                        </TableCell>
                        <TableCell className="whitespace-normal">
                          <div className="max-w-56">
                            <div>{record.model_id}</div>
                            <div className="text-xs text-muted-foreground">{record.provider}</div>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {(record.total_tokens ?? 0).toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right">
                          <CostBadge amount={record.cost_usd} />
                        </TableCell>
                      </TableRow>
                    ))}
                    {records.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                          No AI cost records match the current filters.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Page {page} of {totalPages}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
