import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { MutableRefObject, ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import ForceGraph2D, {
  type ForceGraphMethods,
  type LinkObject,
  type NodeObject,
} from "react-force-graph-2d"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import {
  Bot,
  ChartColumn,
  CircleHelp,
  Crosshair,
  Download,
  FileText,
  GitBranch,
  Info,
  Loader2,
  Map as MapIcon,
  Network,
  PanelRight,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Send,
  Sparkles,
  Table2,
  Wrench,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Markdown } from "@/components/ui/markdown"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { downloadProtectedFile } from "@/lib/protected-file"
import { getCanvasColors, getNodeColor } from "@/lib/theme"
import { useTheme } from "@/lib/theme-provider"
import { useGraphStore } from "@/stores/graph.store"
import { EditNodeDialog } from "@/features/graph/components/EditNodeDialog"
import { NodeDetailSheet } from "@/features/graph/components/NodeDetailSheet"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { cn } from "@/lib/cn"
import { agentAPI } from "../api"
import type { AgentArtifactExportFormat } from "../api"
import type {
  AgentArtifact,
  AgentClarification,
  AgentClientMessage,
  AgentStoredMessage,
  AgentThreadSummary,
  AgentToolTraceItem,
} from "../types"

type Dict = Record<string, unknown>

const AGENT_MODEL_OPTIONS = [
  { id: "gpt-5-mini", name: "GPT-5 Mini", provider: "openai" },
  { id: "gpt-5", name: "GPT-5", provider: "openai" },
] as const

type AgentModelId = (typeof AGENT_MODEL_OPTIONS)[number]["id"]

interface AgentFGNode {
  id: string
  key: string
  label: string
  type: string
  summary?: string
  _degree?: number
}

interface AgentFGLink {
  source: string
  target: string
  type: string
  properties?: Dict
}

type AgentForceNode = NodeObject<AgentFGNode>
type AgentForceLink = LinkObject<AgentFGNode, AgentFGLink>

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function getArtifactGraphLayout(nodeCount: number, linkCount: number, width: number, height: number) {
  const density = linkCount / Math.max(nodeCount, 1)
  const shorterSide = Math.max(320, Math.min(width || 520, height || 420))
  const roomBoost = shorterSide > 720 ? 28 : shorterSide > 520 ? 14 : 0

  return {
    linkDistance: clamp(138 + Math.sqrt(Math.max(nodeCount, 1)) * 15 + density * 18 + roomBoost, 150, 310),
    chargeStrength: -clamp(380 + nodeCount * 8 + density * 70, 440, 1250),
    centerStrength: nodeCount > 35 ? 0.035 : 0.045,
    alphaDecay: nodeCount > 35 ? 0.018 : 0.022,
    velocityDecay: nodeCount > 35 ? 0.44 : 0.38,
    cooldownTime: nodeCount > 35 ? 4200 : 3400,
    warmupTicks: nodeCount > 35 ? 90 : 60,
    zoomPadding: clamp(shorterSide * 0.13, 76, 132),
  }
}

function getArtifactNodeRadius(node: AgentForceNode, nodeCount: number) {
  const degree = node._degree ?? 0
  const denseScale = nodeCount > 30 ? 0.76 : nodeCount > 18 ? 0.86 : 1
  return (4.4 + Math.min(Math.log1p(degree) * 2.3, 6.2)) * denseScale
}

const artifactIcons = {
  graph: Network,
  table: Table2,
  map: MapIcon,
  report: FileText,
  chart: ChartColumn,
} as const

const CHART_COLORS = [
  "#6366F1",
  "#F59E0B",
  "#14B8A6",
  "#EC4899",
  "#8B5CF6",
  "#06B6D4",
  "#84CC16",
  "#F97316",
]

function asArray<T = Dict>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function asRecord(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Dict)
    : {}
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return ""
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function numericValue(value: unknown): number | null {
  if (typeof value === "boolean" || value === null || value === undefined) return null
  if (typeof value === "number") return Number.isFinite(value) ? value : null
  if (typeof value === "string") {
    const parsed = Number(value.replace(/,/g, "").trim())
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function entityKeyFromRecord(value: Dict): string | null {
  for (const key of ["key", "entity_key", "node_key", "target_key", "source_key"]) {
    const candidate = value[key]
    if (typeof candidate === "string" && candidate.trim()) return candidate
  }
  return null
}

function storedToClientMessage(message: AgentStoredMessage): AgentClientMessage | null {
  if (message.role !== "user" && message.role !== "assistant") return null
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    clarification: message.clarification ?? null,
    createdAt: message.created_at,
  }
}

function formatTime(value?: string) {
  if (!value) return ""
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

function formatToolName(name: string) {
  return name.replace(/_/g, " ")
}

function artifactFilename(artifact: AgentArtifact, format: AgentArtifactExportFormat) {
  const slug = artifact.title
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "")
    .slice(0, 80)
  return `${slug || "agent-artifact"}-${artifact.type}.${format}`
}

function firstEntityKeyFromArtifact(artifact: AgentArtifact): string | null {
  if (artifact.type === "graph") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.nodes)[0] ?? {})
  }
  if (artifact.type === "map") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.locations)[0] ?? {})
  }
  if (artifact.type === "table") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.rows)[0] ?? {})
  }
  if (artifact.type === "chart") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.rows)[0] ?? {})
  }
  if (artifact.type === "report") {
    for (const section of asArray<Dict>(artifact.data.sections)) {
      for (const embed of asArray<Dict>(section.embeds)) {
        const data = asRecord(embed.data)
        const key =
          entityKeyFromRecord(asArray<Dict>(data.nodes)[0] ?? {}) ||
          entityKeyFromRecord(asArray<Dict>(data.rows)[0] ?? {})
        if (key) return key
      }
    }
  }
  return null
}

function listText(value: unknown): string[] {
  return asArray<unknown>(value)
    .map((item) => valueText(item).trim())
    .filter(Boolean)
}

function reportColumns(data: Dict, rows: Dict[]): Dict[] {
  const explicitColumns = asArray<Dict>(data.columns)
  if (explicitColumns.length > 0) return explicitColumns

  const keys: string[] = []
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!keys.includes(key)) keys.push(key)
    }
  }
  return keys.slice(0, 8).map((key) => ({ key, label: key.replace(/_/g, " ") }))
}

function reportEmbeddedArtifact(embed: Dict, artifacts: AgentArtifact[]): AgentArtifact | null {
  const existing = artifacts.find((artifact) => artifact.id === valueText(embed.artifact_id))
  if (existing && (existing.type === "graph" || existing.type === "table" || existing.type === "chart")) {
    return existing
  }

  const type = valueText(embed.type)
  if ((type !== "graph" && type !== "table" && type !== "chart") || embed.available === false) return null
  const data = asRecord(embed.data)
  if (Object.keys(data).length === 0) return null

  return {
    id: valueText(embed.artifact_id || embed.id || "embedded-report-artifact"),
    type,
    title: valueText(embed.title || "Embedded artifact"),
    data,
    metadata: asRecord(embed.metadata),
  }
}

function chartSeries(artifact: AgentArtifact) {
  const yKeys = asArray<unknown>(artifact.data.y_keys).map(valueText).filter(Boolean)
  const explicit = asArray<Dict>(artifact.data.series)
  const byKey = new Map(explicit.map((item) => [valueText(item.key), item]))
  return yKeys.map((key, index) => {
    const item = byKey.get(key) ?? {}
    return {
      key,
      label: valueText(item.label || key.replace(/_/g, " ")),
      color: valueText(item.color) || CHART_COLORS[index % CHART_COLORS.length],
      stack: valueText(item.stack),
    }
  })
}

export function AgentPage() {
  const { id: caseId } = useParams()
  const [threads, setThreads] = useState<AgentThreadSummary[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AgentClientMessage[]>([])
  const [artifacts, setArtifacts] = useState<AgentArtifact[]>([])
  const [toolTrace, setToolTrace] = useState<AgentToolTraceItem[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [runStatusText, setRunStatusText] = useState<string | null>(null)
  const [pendingClarification, setPendingClarification] = useState<AgentClarification | null>(null)
  const [selectedModelId, setSelectedModelId] = useState<AgentModelId>("gpt-5-mini")
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null)
  const [detailsPanelOpen, setDetailsPanelOpen] = useState(false)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)

  const selectedArtifact = useMemo(
    () => artifacts.find((artifact) => artifact.id === selectedArtifactId) ?? artifacts[0] ?? null,
    [artifacts, selectedArtifactId]
  )
  const selectedModel =
    AGENT_MODEL_OPTIONS.find((model) => model.id === selectedModelId) ?? AGENT_MODEL_OPTIONS[0]
  const visibleToolTrace = useMemo(
    () => toolTrace.filter((tool) => tool.name !== "request_clarification"),
    [toolTrace]
  )
  const inlineClarificationRunIds = useMemo(() => {
    const ids = new Set<string>()
    messages.forEach((message) => {
      if (message.clarification?.pending_run_id) ids.add(message.clarification.pending_run_id)
    })
    return ids
  }, [messages])
  const activeClarificationMessageId = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index]
      if (message.role === "user") return null
      if (message.clarification) return message.id
    }
    return null
  }, [messages])
  const composerClarification =
    pendingClarification && !inlineClarificationRunIds.has(pendingClarification.pending_run_id)
      ? pendingClarification
      : null

  const handleEntitySelect = useCallback(
    (key: string) => {
      selectNodes([key])
      setDetailsPanelOpen(true)
    },
    [selectNodes]
  )

  const handleArtifactSelect = useCallback(
    (artifact: AgentArtifact) => {
      setSelectedArtifactId(artifact.id)
      const key = firstEntityKeyFromArtifact(artifact)
      if (key) handleEntitySelect(key)
    },
    [handleEntitySelect]
  )

  useEffect(() => {
    if (selectedNodeKeys.size > 0) setDetailsPanelOpen(true)
  }, [selectedNodeKeys])

  const loadThreads = useCallback(async () => {
    if (!caseId) return
    try {
      const nextThreads = await agentAPI.listThreads(caseId)
      setThreads(nextThreads)
    } catch {
      toast.error("Failed to load agent threads")
    }
  }, [caseId])

  useEffect(() => {
    loadThreads()
  }, [loadThreads])

  const loadThread = useCallback(async (threadId: string) => {
    try {
      const thread = await agentAPI.getThread(threadId)
      setActiveThreadId(thread.id)
      setMessages(thread.messages.map(storedToClientMessage).filter(Boolean) as AgentClientMessage[])
      setArtifacts(thread.artifacts)
      setToolTrace([])
      setPendingClarification(null)
      setSelectedArtifactId(thread.artifacts[0]?.id ?? null)
    } catch {
      toast.error("Failed to load agent thread")
    }
  }, [])

  const startNewThread = () => {
    setActiveThreadId(null)
    setMessages([])
    setArtifacts([])
    setToolTrace([])
    setPendingClarification(null)
    setSelectedArtifactId(null)
    setInput("")
    setRunStatusText(null)
    setActiveRunId(null)
  }

  const sendMessage = async (overridePrompt?: string) => {
    const prompt = (overridePrompt ?? input).trim()
    if (!prompt || !caseId || isLoading) return

    const optimisticId = `local_${Date.now()}`
    let committedUserMessageId = optimisticId
    setInput("")
    setPendingClarification(null)
    setIsLoading(true)
    setRunStatusText("Starting agent run")
    setActiveRunId(null)
    setToolTrace([])
    setMessages((current) => [
      ...current,
      { id: optimisticId, role: "user", content: prompt, pending: true },
    ])

    try {
      await agentAPI.streamMessage(
        {
          caseId,
          message: prompt,
          threadId: activeThreadId,
          provider: selectedModel.provider,
          model: selectedModel.id,
        },
        (event) => {
          if (event.type === "run_started") {
            setActiveThreadId(event.thread_id)
            setActiveRunId(event.run_id)
            committedUserMessageId = event.user_message_id ?? optimisticId
            setRunStatusText("Reasoning over the case")
            setMessages((current) =>
              current.map((message) =>
                message.id === optimisticId
                  ? {
                      ...message,
                      id: event.user_message_id ?? optimisticId,
                      pending: false,
                    }
                  : message
              )
            )
          }

          if (event.type === "status") {
            setRunStatusText(event.message)
          }

          if (event.type === "tool_plan") {
            const names = event.tools
              .map((tool) => formatToolName(tool.name || "tool"))
              .join(", ")
            setRunStatusText(names ? `Using ${names}` : "Using tools")
          }

          if (event.type === "tool_result") {
            setToolTrace((current) => [...current, event.tool])
            setRunStatusText(event.tool.summary || `Finished ${formatToolName(event.tool.name)}`)
          }

          if (event.type === "artifact") {
            setArtifacts((current) => {
              const next = [...current.filter((artifact) => artifact.id !== event.artifact.id), event.artifact]
              setSelectedArtifactId((selected) => selected ?? event.artifact.id)
              return next
            })
            setRunStatusText(`Created ${event.artifact.type} artifact`)
          }

          if (event.type === "clarification") {
            setPendingClarification(event.clarification)
            setRunStatusText("Clarification needed")
          }

          if (event.type === "answer") {
            setRunStatusText("Writing final answer")
          }

          if (event.type === "done") {
            const response = event.response
            setActiveThreadId(response.thread_id)
            setMessages((current) => [
              ...current.map((message) =>
                message.id === optimisticId
                  ? { ...message, id: response.user_message_id ?? optimisticId, pending: false }
                  : message
              ),
              {
                id: response.assistant_message_id ?? response.run_id,
                role: "assistant",
                content: response.answer,
                clarification: response.clarification ?? null,
                createdAt: response.created_at,
              },
            ])
            setPendingClarification(null)
            if (response.artifacts.length > 0) {
              setArtifacts(response.artifacts)
              setSelectedArtifactId(response.artifacts[0]?.id ?? null)
            }
            setToolTrace(response.tool_trace)
            setRunStatusText(null)
          }

          if (event.type === "cancelled") {
            setRunStatusText("Run cancelled")
          }

          if (event.type === "error") {
            throw new Error(event.message)
          }
        }
      )
      loadThreads()
    } catch (error) {
      const message = error instanceof Error ? error.message : "Agent request failed"
      setMessages((current) => {
        const next = current.map((item) =>
          item.id === optimisticId || item.id === committedUserMessageId
            ? { ...item, pending: false }
            : item
        )
        return [
          ...next,
          {
            id: `error_${Date.now()}`,
            role: "assistant",
            content: `The run failed before I could write a final response.\n\n${message}`,
            createdAt: new Date().toISOString(),
          },
        ]
      })
      toast.error(message, { duration: 12000 })
    } finally {
      setIsLoading(false)
      setActiveRunId(null)
      setRunStatusText(null)
    }
  }

  const cancelActiveRun = async () => {
    if (!activeRunId) return
    try {
      await agentAPI.cancelRun(activeRunId)
      setRunStatusText("Cancellation requested")
    } catch {
      toast.error("Failed to cancel agent run")
    }
  }

  const activeThreadTitle =
    threads.find((thread) => thread.id === activeThreadId)?.title ?? "New agent thread"

  return (
    <div className="flex h-full min-h-0 bg-background">
      <aside className="hidden w-64 shrink-0 border-r border-border bg-muted/20 md:flex md:flex-col">
        <div className="flex items-center justify-between border-b border-border px-3 py-3">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              AI
            </p>
            <h2 className="truncate text-sm font-semibold text-foreground">
              Agent threads
            </h2>
          </div>
          <Button size="icon" variant="ghost" onClick={startNewThread} aria-label="New agent thread">
            <Plus className="size-4" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {threads.length === 0 ? (
            <div className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
              No agent threads yet.
            </div>
          ) : (
            <div className="space-y-1">
              {threads.map((thread) => (
                <button
                  key={thread.id}
                  type="button"
                  onClick={() => loadThread(thread.id)}
                  className={cn(
                    "w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-muted",
                    activeThreadId === thread.id && "bg-muted text-foreground"
                  )}
                >
                  <span className="block truncate font-medium">{thread.title}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {thread.message_count} messages
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      <ResizablePanelGroup orientation="horizontal" className="min-w-0 flex-1">
        <ResizablePanel id="agent-conversation" order={1} defaultSize={58} minSize={36}>
          <section className="flex h-full min-w-0 flex-col">
            <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-md bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
                  <Bot className="size-4" />
                </div>
                <div className="min-w-0">
                  <h1 className="truncate text-sm font-semibold text-foreground">
                    AI Agent
                  </h1>
                  <p className="truncate text-xs text-muted-foreground">
                    {activeThreadTitle}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Select
                  value={selectedModelId}
                  onValueChange={(value) => setSelectedModelId(value as AgentModelId)}
                  disabled={isLoading}
                >
                  <SelectTrigger
                    className="h-7 w-[132px] rounded-full text-xs"
                    aria-label="Agent model"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align="end">
                    {AGENT_MODEL_OPTIONS.map((model) => (
                      <SelectItem key={model.id} value={model.id} className="text-xs">
                        {model.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Badge variant="outline">
                  {artifacts.length} artifacts
                </Badge>
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
              {messages.length === 0 ? (
                <div className="flex h-full items-center justify-center">
                  <div className="max-w-lg text-center">
                    <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-lg border border-border bg-card">
                      <Sparkles className="size-5 text-amber-600 dark:text-amber-300" />
                    </div>
                    <h2 className="text-sm font-semibold text-foreground">
                      Ask the agent to investigate
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      It can search the graph, inspect documents, run safe read-only Cypher, and build focused views.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
                  {messages.map((message) => (
                    <MessageBubble
                      key={message.id}
                      message={message}
                      onClarificationAnswer={
                        message.id === activeClarificationMessageId && !isLoading
                          ? (answer) => sendMessage(answer)
                          : undefined
                      }
                    />
                  ))}
                  {isLoading && (
                    <ThinkingBubble
                      status={runStatusText}
                      onCancel={activeRunId ? cancelActiveRun : undefined}
                    />
                  )}
                </div>
              )}
            </div>

            {visibleToolTrace.length > 0 && (
              <ToolTrace trace={visibleToolTrace} />
            )}

            <div className="border-t border-border bg-background p-4">
              {composerClarification && (
                <div className="mx-auto mb-3 max-w-3xl">
                  <ClarificationPanel
                    clarification={composerClarification}
                    onAnswer={(answer) => sendMessage(answer)}
                    disabled={isLoading}
                  />
                </div>
              )}
              <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-lg border border-border bg-card p-2 shadow-sm">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault()
                      sendMessage()
                    }
                  }}
                  className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground"
                  placeholder="Ask the agent to answer, explore, or build a focused view..."
                  rows={1}
                  disabled={isLoading}
                />
                <Button size="icon" onClick={() => sendMessage()} disabled={!input.trim() || isLoading} aria-label="Send agent prompt">
                  {isLoading ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                </Button>
              </div>
            </div>
          </section>
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel id="agent-artifacts" order={2} defaultSize={42} minSize={24}>
          <ArtifactWorkspace
            artifacts={artifacts}
            selectedArtifact={selectedArtifact}
            selectedArtifactId={selectedArtifactId}
            onSelectArtifact={handleArtifactSelect}
            exportEnabled={!isLoading}
            onEntitySelect={handleEntitySelect}
          />
        </ResizablePanel>

      </ResizablePanelGroup>
      {detailsPanelOpen ? (
        <aside className="h-full w-[360px] shrink-0">
          <AgentEntityDetailsPanel
            caseId={caseId}
            onClose={() => setDetailsPanelOpen(false)}
          />
        </aside>
      ) : (
        <AgentEntityDetailsRail
          hasSelection={selectedNodeKeys.size > 0}
          onOpen={() => setDetailsPanelOpen(true)}
        />
      )}
    </div>
  )
}

function MessageBubble({
  message,
  onClarificationAnswer,
}: {
  message: AgentClientMessage
  onClarificationAnswer?: (answer: string) => void
}) {
  const isUser = message.role === "user"
  const clarificationQuestion = message.clarification?.question.trim()
  const repeatsClarification =
    !isUser &&
    Boolean(clarificationQuestion) &&
    message.content.trim() === clarificationQuestion
  const showClarificationPanel = !isUser && Boolean(message.clarification && onClarificationAnswer)
  const hideMessageBodyForPanel = showClarificationPanel && repeatsClarification

  if (isUser) {
    return (
      <article className="flex justify-end">
        <div className="max-w-[82%] rounded-lg border border-slate-900 bg-slate-900 px-3 py-2 text-sm text-white shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-50 sm:max-w-[68%]">
          <p className="whitespace-pre-wrap">{message.content}</p>
          <div className="mt-1 text-[11px] text-white/70 dark:text-slate-300">
            {message.pending ? "Sending..." : formatTime(message.createdAt)}
          </div>
        </div>
      </article>
    )
  }

  return (
    <article className="flex gap-3">
      <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground ring-1 ring-border/60">
        <Bot className="size-4" />
      </div>
      <div className="min-w-0 flex-1 py-0.5 text-sm text-foreground">
        {!hideMessageBodyForPanel ? (
          <Markdown
            content={message.content}
            className="max-w-none leading-6 [overflow-wrap:anywhere]"
          />
        ) : null}
        {showClarificationPanel && message.clarification && onClarificationAnswer && (
          <div className={cn("max-w-3xl", !hideMessageBodyForPanel && "mt-3")}>
            <ClarificationPanel
              clarification={message.clarification}
              onAnswer={onClarificationAnswer}
            />
          </div>
        )}
        <div className="mt-1 text-[11px] text-muted-foreground">
          {formatTime(message.createdAt)}
        </div>
      </div>
    </article>
  )
}

function ClarificationPanel({
  clarification,
  onAnswer,
  disabled = false,
}: {
  clarification: AgentClarification
  onAnswer: (answer: string) => void
  disabled?: boolean
}) {
  const [customAnswer, setCustomAnswer] = useState("")
  const sendCustomAnswer = () => {
    const answer = customAnswer.trim()
    if (!answer || disabled) return
    setCustomAnswer("")
    onAnswer(answer)
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card text-card-foreground shadow-sm">
      <div className="flex gap-3 border-b border-border bg-muted/30 px-3 py-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-background text-amber-700 ring-1 ring-border dark:text-amber-300">
          <CircleHelp className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Clarification needed
          </div>
          <div className="mt-0.5 text-sm font-medium leading-5 text-foreground">
            {clarification.question}
          </div>
        </div>
      </div>
      <div className="space-y-3 p-3">
        <div className="grid gap-2 sm:grid-cols-2">
          {clarification.options.map((option) => (
            <Button
              key={option.id}
              type="button"
              size="sm"
              variant="outline"
              className="h-auto min-h-10 justify-start whitespace-normal rounded-md border-border bg-background px-3 py-2 text-left text-xs font-medium leading-snug text-foreground shadow-none hover:border-amber-300 hover:bg-amber-50 hover:text-amber-950 dark:hover:border-amber-500/50 dark:hover:bg-amber-500/10 dark:hover:text-amber-100"
              disabled={disabled}
              title={option.description ?? option.label}
              onClick={() => onAnswer(option.label)}
            >
              <span className="min-w-0">{option.label}</span>
            </Button>
          ))}
        </div>
        {clarification.allow_free_text && (
          <div className="flex gap-2">
            <input
              value={customAnswer}
              onChange={(event) => setCustomAnswer(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault()
                  sendCustomAnswer()
                }
              }}
              className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-amber-400 focus:ring-2 focus:ring-amber-100 dark:focus:ring-amber-500/20"
              placeholder="Type your own answer"
              disabled={disabled}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-9 w-9 shrink-0 p-0"
              disabled={disabled || !customAnswer.trim()}
              onClick={sendCustomAnswer}
              aria-label="Send custom clarification answer"
            >
              <Send className="size-3.5" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function AgentEntityDetailsRail({
  hasSelection,
  onOpen,
}: {
  hasSelection: boolean
  onOpen: () => void
}) {
  return (
    <aside className="flex h-full w-12 shrink-0 flex-col items-center gap-1 border-l border-border bg-muted/30 pt-2">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className={cn("relative", hasSelection && "text-foreground")}
        onClick={onOpen}
        title="Entity details"
      >
        <Info className="size-4" />
        {hasSelection && (
          <span className="absolute -left-1 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-amber-500" />
        )}
      </Button>
    </aside>
  )
}

function AgentEntityDetailsPanel({
  caseId,
  onClose,
}: {
  caseId?: string
  onClose: () => void
}) {
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const [editNodeKey, setEditNodeKey] = useState<string | null>(null)

  return (
    <section className="flex h-full min-w-0 flex-col border-l border-border bg-card">
      <header className="flex items-center justify-between border-b border-border bg-muted/30 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Info className="size-4 text-muted-foreground" />
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-foreground">
              Entity details
            </h2>
            <p className="truncate text-xs text-muted-foreground">
              {selectedNodeKeys.size > 0
                ? `${selectedNodeKeys.size} selected`
                : "Select an entity in an artifact"}
            </p>
          </div>
        </div>
        <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} title="Collapse details">
          <PanelRightClose className="size-3.5" />
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">
        {caseId && selectedNodeKeys.size > 0 ? (
          <NodeDetailSheet
            caseId={caseId}
            onEditNode={(nodeKey) => setEditNodeKey(nodeKey)}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <PanelRightOpen className="size-8 text-muted-foreground/40" />
            <p className="text-sm font-medium text-muted-foreground">
              Select an entity to inspect it
            </p>
            <p className="text-xs text-muted-foreground/70">
              Click graph nodes, table rows, or map points.
            </p>
          </div>
        )}
      </div>

      <EditNodeDialog
        open={!!editNodeKey}
        onOpenChange={(open) => !open && setEditNodeKey(null)}
        nodeKey={editNodeKey}
        caseId={caseId ?? ""}
      />
    </section>
  )
}

function ThinkingBubble({
  status,
  onCancel,
}: {
  status?: string | null
  onCancel?: () => void
}) {
  return (
    <div className="flex gap-3">
      <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Bot className="size-4" />
      </div>
      <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" />
          {status || "Working through the case data"}
        </div>
        {onCancel && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={onCancel}
          >
            <X className="mr-1 size-3" />
            Cancel
          </Button>
        )}
      </div>
    </div>
  )
}

function ToolTrace({ trace }: { trace: AgentToolTraceItem[] }) {
  return (
    <div className="border-t border-border bg-muted/20 px-4 py-2">
      <div className="mx-auto max-w-3xl">
        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Wrench className="size-3.5" />
          Tool trace
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {trace.map((item) => (
            <div
              key={item.id}
              className="min-w-48 rounded-md border border-border bg-background px-2.5 py-2 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-foreground">
                  {formatToolName(item.name)}
                </span>
                <Badge variant={item.status === "success" ? "secondary" : "destructive"} className="text-[10px]">
                  {item.duration_ms}ms
                </Badge>
              </div>
              <p className="mt-1 line-clamp-2 text-muted-foreground">
                {item.error || item.summary || "Completed"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ArtifactWorkspace({
  artifacts,
  selectedArtifact,
  selectedArtifactId,
  onSelectArtifact,
  exportEnabled,
  onEntitySelect,
}: {
  artifacts: AgentArtifact[]
  selectedArtifact: AgentArtifact | null
  selectedArtifactId: string | null
  onSelectArtifact: (artifact: AgentArtifact) => void
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  return (
    <section className="flex h-full min-w-0 flex-col bg-muted/10">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <PanelRight className="size-4 text-muted-foreground" />
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-foreground">
              Agent artifacts
            </h2>
            <p className="truncate text-xs text-muted-foreground">
              Focused views generated from tool results
            </p>
          </div>
        </div>
      </header>

      {artifacts.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-6">
          <div className="max-w-sm text-center">
            <div className="mx-auto mb-3 flex size-10 items-center justify-center rounded-lg border border-dashed border-border">
              <GitBranch className="size-4 text-muted-foreground" />
            </div>
            <h3 className="text-sm font-medium text-foreground">
              No artifact yet
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Ask for a graph, table, chart, report, or map view.
            </p>
          </div>
        </div>
      ) : (
        <>
          <div className="flex gap-2 overflow-x-auto border-b border-border px-3 py-2">
            {artifacts.map((artifact) => {
              const Icon = artifactIcons[artifact.type] ?? FileText
              return (
                <button
                  key={artifact.id}
                  type="button"
                  onClick={() => onSelectArtifact(artifact)}
                  className={cn(
                    "flex min-w-36 items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition-colors",
                    selectedArtifactId === artifact.id
                      ? "border-primary/40 bg-primary/10 text-foreground"
                      : "border-border bg-background text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon className="size-3.5 shrink-0" />
                  <span className="truncate font-medium">{artifact.title}</span>
                </button>
              )
            })}
          </div>
          <div className="flex min-h-0 flex-1 px-4 py-3">
            {selectedArtifact && (
              <ArtifactRenderer
                artifact={selectedArtifact}
                artifacts={artifacts}
                exportEnabled={exportEnabled}
                onEntitySelect={onEntitySelect}
              />
            )}
          </div>
        </>
      )}
    </section>
  )
}

function ArtifactRenderer({
  artifact,
  artifacts,
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  artifacts: AgentArtifact[]
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  if (artifact.type === "graph") return <GraphArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "table") return <TableArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "map") return <MapArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "report") return <ReportArtifact artifact={artifact} artifacts={artifacts} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "chart") return <ChartArtifact artifact={artifact} exportEnabled={exportEnabled} />
  return <pre className="h-full overflow-auto text-xs">{JSON.stringify(artifact.data, null, 2)}</pre>
}

function ArtifactShell({
  artifact,
  children,
  exportEnabled,
  headerActions,
}: {
  artifact: AgentArtifact
  children: ReactNode
  exportEnabled: boolean
  headerActions?: ReactNode
}) {
  const Icon = artifactIcons[artifact.type] ?? FileText
  const [isDownloading, setIsDownloading] = useState(false)
  const exportFormats: AgentArtifactExportFormat[] =
    artifact.type === "report" ? ["pdf", "docx"] : ["csv"]

  const downloadArtifact = async (format: AgentArtifactExportFormat) => {
    if (!exportEnabled || isDownloading) return
    setIsDownloading(true)
    try {
      await downloadProtectedFile(
        agentAPI.artifactExportUrl(artifact.id, format),
        artifactFilename(artifact, format)
      )
      toast.success(`${format.toUpperCase()} export downloaded`)
    } catch (error) {
      const message = error instanceof Error ? error.message : `Failed to download ${format.toUpperCase()}`
      toast.error(message)
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-border/70 px-1 pb-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="size-4 text-muted-foreground" />
          <h3 className="truncate text-sm font-semibold text-foreground">
            {artifact.title}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {headerActions}
          {exportFormats.map((format) => (
            <Button
              key={format}
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => downloadArtifact(format)}
              disabled={!exportEnabled || isDownloading}
              title={exportEnabled ? `Download ${format.toUpperCase()}` : "Exports are available when the run finishes"}
            >
              {isDownloading ? (
                <Loader2 className="mr-1 size-3 animate-spin" />
              ) : (
                <Download className="mr-1 size-3" />
              )}
              {format === "docx" ? "Word" : format.toUpperCase()}
            </Button>
          ))}
          <Badge variant="secondary" className="capitalize">
            {artifact.type}
          </Badge>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col pt-3">{children}</div>
    </div>
  )
}

function GraphArtifact({
  artifact,
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  const rawNodes = asArray<Dict>(artifact.data.nodes)
  const rawLinks = asArray<Dict>(artifact.data.links)
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraphMethods<AgentFGNode, AgentFGLink> | undefined>(undefined)
  const [dimensions, setDimensions] = useState({ width: 520, height: 420 })
  const { id: caseId } = useParams()
  const navigate = useNavigate()
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const clearSubgraph = useGraphStore((s) => s.clearSubgraph)
  const addToSubgraph = useGraphStore((s) => s.addToSubgraph)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const setSpotlightVisible = useGraphStore((s) => s.setSpotlightVisible)
  const { theme } = useTheme()
  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)
  const canvasColors = getCanvasColors(isDark)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setDimensions({ width, height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const graphData = useMemo<{ nodes: AgentForceNode[]; links: AgentForceLink[] }>(() => {
    const endpointLookup = new Map<string, string>()
    const degreeCounts = new Map<string, number>()
    const nodes: AgentForceNode[] = rawNodes.map((node, index) => {
      const key = valueText(node.key || node.id || `node_${index}`)
      const label = valueText(node.name || node.label || key)
      endpointLookup.set(key, key)
      if (node.id != null) endpointLookup.set(valueText(node.id), key)
      if (node.name != null) endpointLookup.set(valueText(node.name), key)
      return {
        id: key,
        key,
        label,
        type: valueText(node.type || "entity").toLowerCase(),
        summary: valueText(node.summary),
      }
    })

    const links = rawLinks
      .map((link) => {
        const source = endpointLookup.get(valueText(link.source)) ?? valueText(link.source)
        const target = endpointLookup.get(valueText(link.target)) ?? valueText(link.target)
        if (!source || !target) return null
        degreeCounts.set(source, (degreeCounts.get(source) ?? 0) + 1)
        degreeCounts.set(target, (degreeCounts.get(target) ?? 0) + 1)
        return {
          source,
          target,
          type: valueText(link.type || link.relationship || "RELATED_TO"),
          properties: asRecord(link.properties),
        }
      })
      .filter(Boolean) as AgentForceLink[]

    return {
      nodes: nodes.map((node) => ({ ...node, _degree: degreeCounts.get(node.key) ?? 0 })),
      links,
    }
  }, [rawNodes, rawLinks])

  const layout = useMemo(
    () =>
      getArtifactGraphLayout(
        graphData.nodes.length,
        graphData.links.length,
        dimensions.width,
        dimensions.height
      ),
    [dimensions.height, dimensions.width, graphData.links.length, graphData.nodes.length]
  )

  useEffect(() => {
    const graph = graphRef.current
    if (!graph || graphData.nodes.length === 0) return

    const linkForce = graph.d3Force("link")
    linkForce?.distance(layout.linkDistance)
    linkForce?.strength?.(graphData.nodes.length > 35 ? 0.34 : 0.42)

    graph.d3Force("charge")?.strength(layout.chargeStrength)
    graph.d3Force("center")?.strength(layout.centerStrength)
    graph.d3ReheatSimulation()
  }, [
    graphData.links.length,
    graphData.nodes.length,
    layout.centerStrength,
    layout.chargeStrength,
    layout.linkDistance,
  ])

  useEffect(() => {
    if (graphData.nodes.length === 0) return
    const fitTimer = window.setTimeout(() => {
      graphRef.current?.zoomToFit(550, layout.zoomPadding)
    }, 900)
    return () => window.clearTimeout(fitTimer)
  }, [graphData.nodes.length, graphData.links.length, layout.zoomPadding])

  const spotlightKeys = useMemo(
    () => Array.from(new Set(graphData.nodes.map((node) => node.key).filter(Boolean))),
    [graphData.nodes]
  )

  const openInSpotlight = useCallback(() => {
    if (!caseId || spotlightKeys.length === 0) return
    clearSubgraph()
    addToSubgraph(spotlightKeys)
    setSpotlightVisible(true)
    selectNodes(spotlightKeys)
    navigate(`/cases/${caseId}/graph`, {
      state: {
        workspaceGraphSource: {
          sourceType: "Agent artifact",
          sourceId: artifact.id,
          sourceLabel: artifact.title,
          entityKeys: spotlightKeys,
        },
      },
    })
  }, [
    addToSubgraph,
    artifact.id,
    artifact.title,
    caseId,
    clearSubgraph,
    navigate,
    selectNodes,
    setSpotlightVisible,
    spotlightKeys,
  ])

  const paintNode = useCallback(
    (node: AgentForceNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x ?? 0
      const y = node.y ?? 0
      const isSelected = selectedNodeKeys.has(node.key)
      const nodeCount = graphData.nodes.length
      const radius = getArtifactNodeRadius(node, nodeCount)

      if (isSelected) {
        ctx.beginPath()
        ctx.arc(x, y, radius + 4, 0, 2 * Math.PI)
        ctx.strokeStyle = "#f59e0b"
        ctx.lineWidth = 2 / globalScale
        ctx.stroke()
      }

      ctx.beginPath()
      ctx.arc(x, y, radius, 0, 2 * Math.PI)
      ctx.fillStyle = getNodeColor(node.type)
      ctx.fill()

      ctx.beginPath()
      ctx.arc(x, y, radius, 0, 2 * Math.PI)
      ctx.strokeStyle = canvasColors.background
      ctx.lineWidth = 2 / globalScale
      ctx.stroke()

      const degree = node._degree ?? 0
      const labelScaleThreshold = nodeCount > 28 ? 1.25 : nodeCount > 16 ? 1.08 : 0
      const shouldShowLabel =
        isSelected || labelScaleThreshold === 0 || globalScale >= labelScaleThreshold || degree >= 4

      if (!shouldShowLabel) return

      const fontSize = Math.max(9 / globalScale, 2.4)
      ctx.font = `${fontSize}px Inter, system-ui, sans-serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "top"
      ctx.fillStyle = canvasColors.labelText
      const label = node.label.length > 26 ? `${node.label.slice(0, 24)}...` : node.label
      ctx.fillText(label, x, y + radius + 3)
    },
    [canvasColors, graphData.nodes.length, selectedNodeKeys]
  )

  const paintLink = useCallback(
    (link: AgentForceLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const source = link.source as AgentForceNode
      const target = link.target as AgentForceNode
      if (source?.x == null || source.y == null || target?.x == null || target.y == null) return

      ctx.save()
      ctx.beginPath()
      ctx.moveTo(source.x, source.y)
      ctx.lineTo(target.x, target.y)
      ctx.strokeStyle = canvasColors.linkColor
      ctx.globalAlpha = graphData.links.length > 35 ? 0.26 : 0.36
      ctx.lineWidth = Math.max(0.8 / Math.sqrt(globalScale), 0.45)
      ctx.stroke()

      const dx = target.x - source.x
      const dy = target.y - source.y
      const length = Math.sqrt(dx * dx + dy * dy)
      if (length > 1) {
        const angle = Math.atan2(dy, dx)
        const arrowLen = 5 / globalScale
        const targetRadius = getArtifactNodeRadius(target, graphData.nodes.length)
        const endX = target.x - (dx / length) * (targetRadius + 3)
        const endY = target.y - (dy / length) * (targetRadius + 3)
        ctx.beginPath()
        ctx.moveTo(endX, endY)
        ctx.lineTo(
          endX - arrowLen * Math.cos(angle - 0.45),
          endY - arrowLen * Math.sin(angle - 0.45)
        )
        ctx.lineTo(
          endX - arrowLen * Math.cos(angle + 0.45),
          endY - arrowLen * Math.sin(angle + 0.45)
        )
        ctx.closePath()
        ctx.fillStyle = canvasColors.linkColor
        ctx.fill()
      }

      const showLinkLabel =
        link.type &&
        length > 44 / Math.max(globalScale, 0.1) &&
        (graphData.links.length <= 12 ||
          globalScale >= (graphData.links.length > 35 ? 1.65 : 1.25))

      if (showLinkLabel) {
        const midX = (source.x + target.x) / 2
        const midY = (source.y + target.y) / 2
        const fontSize = Math.max(8 / globalScale, 2)
        const text = link.type.length > 28 ? `${link.type.slice(0, 26)}...` : link.type
        ctx.font = `${fontSize}px Inter, system-ui, sans-serif`
        const metrics = ctx.measureText(text)
        const padX = 3 / globalScale
        const padY = 2 / globalScale
        ctx.globalAlpha = 0.9
        ctx.fillStyle = canvasColors.labelBg
        ctx.fillRect(
          midX - metrics.width / 2 - padX,
          midY - fontSize / 2 - padY,
          metrics.width + padX * 2,
          fontSize + padY * 2
        )
        ctx.fillStyle = canvasColors.labelText
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.fillText(text, midX, midY)
      }

      ctx.restore()
    },
    [canvasColors, graphData.links.length, graphData.nodes.length]
  )

  return (
    <ArtifactShell
      artifact={artifact}
      exportEnabled={exportEnabled}
      headerActions={
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={openInSpotlight}
          disabled={spotlightKeys.length === 0}
          title="Open these nodes in the main graph spotlight"
        >
          <Crosshair className="mr-1 size-3" />
          Spotlight
        </Button>
      }
    >
      <div
        ref={containerRef}
        className="min-h-[320px] flex-1 overflow-hidden rounded-md border border-border bg-slate-100 dark:bg-slate-950"
      >
        {graphData.nodes.length === 0 ? (
          <SmallEmpty label="No graph nodes returned" />
        ) : (
          <ForceGraph2D
            ref={graphRef as MutableRefObject<ForceGraphMethods<AgentFGNode, AgentFGLink>>}
            graphData={graphData}
            width={dimensions.width}
            height={dimensions.height}
            backgroundColor={canvasColors.background}
            nodeCanvasObject={paintNode}
            nodePointerAreaPaint={(node: AgentForceNode, color, ctx) => {
              const radius = getArtifactNodeRadius(node, graphData.nodes.length)
              ctx.beginPath()
              ctx.arc(node.x ?? 0, node.y ?? 0, radius + 5, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()
            }}
            linkCanvasObject={paintLink}
            linkDirectionalParticles={0}
            onNodeClick={(node) => onEntitySelect(node.key)}
            onEngineStop={() => graphRef.current?.zoomToFit(450, layout.zoomPadding)}
            cooldownTime={layout.cooldownTime}
            warmupTicks={layout.warmupTicks}
            d3AlphaDecay={layout.alphaDecay}
            d3VelocityDecay={layout.velocityDecay}
            enableNodeDrag
          />
        )}
      </div>
      <div className="mt-3 grid shrink-0 grid-cols-2 gap-2 text-xs">
        <Stat label="Nodes" value={graphData.nodes.length} />
        <Stat label="Relationships" value={graphData.links.length} />
      </div>
    </ArtifactShell>
  )
}

function ChartPreview({ artifact }: { artifact: AgentArtifact }) {
  const rows = asArray<Dict>(artifact.data.rows)
  const rawType = valueText(artifact.data.chart_type)
  const chartType = ["bar", "stacked_bar", "line", "area", "pie", "donut", "scatter"].includes(rawType)
    ? rawType
    : "bar"
  const xKey = valueText(artifact.data.x_key)
  const categoryKey = valueText(artifact.data.category_key)
  const valueKey = valueText(artifact.data.value_key)
  const xLabel = valueText(artifact.data.x_label || xKey || categoryKey)
  const yLabel = valueText(artifact.data.y_label || valueKey)
  const series = chartSeries(artifact)
  const chartData = useMemo(
    () =>
      rows.map((row) => {
        const normalized: Dict = { ...row }
        for (const item of series) {
          normalized[item.key] = numericValue(row[item.key])
        }
        if (valueKey) normalized[valueKey] = numericValue(row[valueKey])
        if (xKey && chartType === "scatter") normalized[xKey] = numericValue(row[xKey])
        return normalized
      }),
    [chartType, rows, series, valueKey, xKey]
  )
  const pieData = useMemo(
    () =>
      rows
        .map((row) => ({
          name: valueText(row[categoryKey] || "Unknown"),
          value: numericValue(row[valueKey]) ?? 0,
        }))
        .filter((item) => item.value !== 0),
    [categoryKey, rows, valueKey]
  )

  const axisTick = { fill: "var(--muted-foreground)", fontSize: 11 }
  const tooltipStyle = {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    borderRadius: "8px",
    color: "var(--popover-foreground)",
    fontSize: "12px",
  }

  const chartBody = () => {
    if (rows.length === 0) return <SmallEmpty label="No chart rows returned" />
    if (chartType === "pie" || chartType === "donut") {
      if (!categoryKey || !valueKey || pieData.length === 0) {
        return <SmallEmpty label="No pie chart values returned" />
      }
      return (
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              innerRadius={chartType === "donut" ? "52%" : 0}
              outerRadius="78%"
              paddingAngle={chartType === "donut" ? 2 : 1}
              label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
              labelLine={false}
            >
              {pieData.map((_, index) => (
                <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      )
    }

    if (!xKey || series.length === 0) {
      return <SmallEmpty label="No chart axes returned" />
    }

    if (chartType === "line") {
      return (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 12, right: 18, left: 4, bottom: 12 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey={xKey} tick={axisTick} label={xLabel ? { value: xLabel, position: "insideBottom", offset: -8 } : undefined} />
            <YAxis tick={axisTick} width={56} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft" } : undefined} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {series.map((item) => (
              <Line key={item.key} type="monotone" dataKey={item.key} name={item.label} stroke={item.color} strokeWidth={2.2} dot={{ r: 2.8 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )
    }

    if (chartType === "area") {
      return (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 12, right: 18, left: 4, bottom: 12 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey={xKey} tick={axisTick} label={xLabel ? { value: xLabel, position: "insideBottom", offset: -8 } : undefined} />
            <YAxis tick={axisTick} width={56} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft" } : undefined} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {series.map((item) => (
              <Area key={item.key} type="monotone" dataKey={item.key} name={item.label} stroke={item.color} fill={item.color} fillOpacity={0.22} strokeWidth={2} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )
    }

    if (chartType === "scatter") {
      return (
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 12, right: 18, left: 4, bottom: 12 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis type="number" dataKey="x" name={xLabel || xKey} tick={axisTick} />
            <YAxis type="number" dataKey="y" name={yLabel || series[0]?.label} tick={axisTick} width={56} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ strokeDasharray: "3 3" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {series.map((item) => (
              <Scatter
                key={item.key}
                name={item.label}
                fill={item.color}
                data={chartData
                  .map((row) => ({ x: numericValue(row[xKey]), y: numericValue(row[item.key]) }))
                  .filter((point) => point.x !== null && point.y !== null)}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      )
    }

    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 12, right: 18, left: 4, bottom: 12 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis dataKey={xKey} tick={axisTick} label={xLabel ? { value: xLabel, position: "insideBottom", offset: -8 } : undefined} />
          <YAxis tick={axisTick} width={56} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft" } : undefined} />
          <Tooltip contentStyle={tooltipStyle} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {series.map((item) => (
            <Bar
              key={item.key}
              dataKey={item.key}
              name={item.label}
              fill={item.color}
              radius={chartType === "stacked_bar" ? [0, 0, 0, 0] : [4, 4, 0, 0]}
              stackId={chartType === "stacked_bar" ? item.stack || "total" : undefined}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  return chartBody()
}

function ChartArtifact({
  artifact,
  exportEnabled,
}: {
  artifact: AgentArtifact
  exportEnabled: boolean
}) {
  const rows = asArray<Dict>(artifact.data.rows)
  const rawType = valueText(artifact.data.chart_type)
  const chartType = ["bar", "stacked_bar", "line", "area", "pie", "donut", "scatter"].includes(rawType)
    ? rawType
    : "bar"
  const valueKey = valueText(artifact.data.value_key)
  const series = chartSeries(artifact)
  const notes = valueText(artifact.data.notes).trim()

  return (
    <ArtifactShell artifact={artifact} exportEnabled={exportEnabled}>
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="grid shrink-0 grid-cols-3 gap-2 text-xs">
          <Stat label="Type" value={chartType.replace("_", " ")} />
          <Stat label="Rows" value={rows.length} />
          <Stat label="Series" value={Math.max(series.length, valueKey ? 1 : 0)} />
        </div>
        {notes && (
          <p className="shrink-0 border-l-2 border-amber-500/70 pl-3 text-xs leading-5 text-muted-foreground">
            {notes}
          </p>
        )}
        <div className="min-h-[360px] flex-1 rounded-md bg-muted/20 p-3 text-muted-foreground">
          <ChartPreview artifact={artifact} />
        </div>
      </div>
    </ArtifactShell>
  )
}

function ReportArtifact({
  artifact,
  artifacts,
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  artifacts: AgentArtifact[]
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  const sections = asArray<Dict>(artifact.data.sections)
  const includedItems = listText(artifact.data.included_items)
  const openQuestions = listText(artifact.data.open_questions)
  const purpose = valueText(artifact.data.purpose).trim()
  const scope = valueText(artifact.data.scope).trim()
  const audience = valueText(artifact.data.audience).trim()
  const revisionNote = valueText(artifact.metadata.revision_note).trim()

  return (
    <ArtifactShell artifact={artifact} exportEnabled={exportEnabled}>
      <article className="min-h-0 flex-1 overflow-y-auto px-1 pb-6 pr-3">
        <div className="mx-auto max-w-3xl">
          <div className="border-b border-border/70 pb-4">
            <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
              <span>Report draft</span>
              {audience && <span className="normal-case tracking-normal">For {audience}</span>}
            </div>
            {purpose && (
              <p className="mt-2 text-sm leading-6 text-foreground">
                {purpose}
              </p>
            )}
            {(scope || revisionNote) && (
              <div className="mt-3 space-y-2 border-l-2 border-amber-500/70 pl-3 text-xs leading-5 text-muted-foreground">
                {scope && <p>{scope}</p>}
                {revisionNote && <p>Revision: {revisionNote}</p>}
              </div>
            )}
            {includedItems.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {includedItems.slice(0, 12).map((item) => (
                  <span
                    key={item}
                    className="rounded-md bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground"
                  >
                    {item}
                  </span>
                ))}
              </div>
            )}
          </div>

          {sections.length === 0 ? (
            <div className="py-8">
              <SmallEmpty label="No report sections returned" />
            </div>
          ) : (
            <div className="divide-y divide-border/70">
              {sections.map((section, index) => {
                const embeds = asArray<Dict>(section.embeds)
                return (
                  <section key={valueText(section.id || section.heading || index)} className="py-5">
                    <h2 className="text-base font-semibold text-foreground">
                      {valueText(section.heading || `Section ${index + 1}`)}
                    </h2>
                    <Markdown
                      content={valueText(section.content)}
                      className="mt-2 max-w-none text-sm leading-6 text-foreground [overflow-wrap:anywhere]"
                    />
                    {embeds.length > 0 && (
                      <div className="mt-4 space-y-4">
                        {embeds.map((embed, embedIndex) => (
                          <ReportEmbedBlock
                            key={valueText(embed.artifact_id || embedIndex)}
                            embed={embed}
                            artifacts={artifacts}
                            onEntitySelect={onEntitySelect}
                          />
                        ))}
                      </div>
                    )}
                  </section>
                )
              })}
            </div>
          )}

          {openQuestions.length > 0 && (
            <section className="mt-2 border-t border-border/70 pt-5">
              <h2 className="text-sm font-semibold text-foreground">Open questions</h2>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-sm leading-6 text-muted-foreground">
                {openQuestions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </article>
    </ArtifactShell>
  )
}

function ReportEmbedBlock({
  embed,
  artifacts,
  onEntitySelect,
}: {
  embed: Dict
  artifacts: AgentArtifact[]
  onEntitySelect: (key: string) => void
}) {
  const artifact = reportEmbeddedArtifact(embed, artifacts)
  const caption = valueText(embed.caption).trim()

  if (!artifact) {
    return (
      <figure className="border-y border-border/70 py-3">
        <figcaption className="text-xs font-medium text-muted-foreground">
          {valueText(embed.title || "Referenced artifact")}
        </figcaption>
        <p className="mt-1 text-xs text-muted-foreground">
          {valueText(embed.reason || "This embedded artifact is not available in the report snapshot.")}
        </p>
      </figure>
    )
  }

  if (artifact.type === "graph") {
    return (
      <ReportGraphEmbed
        artifact={artifact}
        caption={caption}
        onEntitySelect={onEntitySelect}
      />
    )
  }

  if (artifact.type === "chart") {
    return (
      <ReportChartEmbed
        artifact={artifact}
        caption={caption}
      />
    )
  }

  return (
    <ReportTableEmbed
      artifact={artifact}
      caption={caption}
      onEntitySelect={onEntitySelect}
    />
  )
}

function ReportChartEmbed({
  artifact,
  caption,
}: {
  artifact: AgentArtifact
  caption: string
}) {
  const rows = asArray<Dict>(artifact.data.rows)
  const chartType = valueText(artifact.data.chart_type || "chart").replace("_", " ")

  return (
    <figure className="border-y border-border/70 py-3">
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-semibold text-foreground">Chart: {artifact.title}</span>
        <span className="text-muted-foreground">
          {chartType} · {rows.length} rows
        </span>
      </figcaption>
      {caption && <p className="mt-1 text-xs leading-5 text-muted-foreground">{caption}</p>}
      <div className="mt-3 h-80 rounded-md bg-muted/20 p-3 text-muted-foreground">
        <ChartPreview artifact={artifact} />
      </div>
    </figure>
  )
}

function ReportTableEmbed({
  artifact,
  caption,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  caption: string
  onEntitySelect: (key: string) => void
}) {
  const rows = asArray<Dict>(artifact.data.rows)
  const columns = reportColumns(artifact.data, rows).slice(0, 8)
  return (
    <figure className="border-y border-border/70 py-3">
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-semibold text-foreground">Table: {artifact.title}</span>
        <span className="text-muted-foreground">{rows.length} rows</span>
      </figcaption>
      {caption && <p className="mt-1 text-xs leading-5 text-muted-foreground">{caption}</p>}
      {rows.length === 0 ? (
        <div className="mt-3">
          <SmallEmpty label="No embedded table rows" />
        </div>
      ) : (
        <div className="mt-3 max-h-80 overflow-auto">
          <table className="w-max min-w-full border-separate border-spacing-0 text-xs">
            <thead className="sticky top-0 z-10 bg-background/95 backdrop-blur">
              <tr>
                {columns.map((column) => (
                  <th
                    key={valueText(column.key)}
                    className="whitespace-nowrap border-b border-border/70 px-3 py-2 text-left font-semibold text-foreground"
                  >
                    {valueText(column.label || column.key)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 12).map((row, rowIndex) => {
                const key = entityKeyFromRecord(row)
                return (
                  <tr
                    key={rowIndex}
                    onClick={() => key && onEntitySelect(key)}
                    className={cn(key && "cursor-pointer hover:bg-muted/45")}
                  >
                    {columns.map((column) => {
                      const cellText = valueText(row[valueText(column.key)]).slice(0, 160)
                      return (
                        <td
                          key={valueText(column.key)}
                          className="max-w-72 truncate border-b border-border/50 px-3 py-2 align-top leading-5 text-muted-foreground"
                          title={cellText}
                        >
                          {cellText}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  )
}

function ReportGraphEmbed({
  artifact,
  caption,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  caption: string
  onEntitySelect: (key: string) => void
}) {
  const rawNodes = asArray<Dict>(artifact.data.nodes)
  const rawLinks = asArray<Dict>(artifact.data.links)
  const nodes = rawNodes.slice(0, 18).map((node, index) => {
    const key = valueText(node.key || node.id || `node-${index}`)
    return {
      key,
      label: valueText(node.name || node.label || key),
      type: valueText(node.type || "entity").toLowerCase(),
    }
  })
  const endpointLookup = new Map<string, string>()
  nodes.forEach((node) => {
    endpointLookup.set(node.key, node.key)
    endpointLookup.set(node.label, node.key)
  })
  const links = rawLinks
    .slice(0, 36)
    .map((link) => ({
      source: endpointLookup.get(valueText(link.source)) ?? valueText(link.source),
      target: endpointLookup.get(valueText(link.target)) ?? valueText(link.target),
    }))
    .filter((link) => endpointLookup.has(link.source) && endpointLookup.has(link.target))

  const width = 560
  const height = 230
  const centerX = width / 2
  const centerY = height / 2
  const radius = nodes.length <= 2 ? 54 : Math.min(92, 46 + nodes.length * 2.6)
  const positions = new Map(
    nodes.map((node, index) => {
      if (nodes.length === 1) return [node.key, { x: centerX, y: centerY }]
      const angle = -Math.PI / 2 + (index / nodes.length) * Math.PI * 2
      return [
        node.key,
        {
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius,
        },
      ]
    })
  )

  return (
    <figure className="border-y border-border/70 py-3">
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-semibold text-foreground">Graph: {artifact.title}</span>
        <span className="text-muted-foreground">
          {rawNodes.length} nodes, {rawLinks.length} relationships
        </span>
      </figcaption>
      {caption && <p className="mt-1 text-xs leading-5 text-muted-foreground">{caption}</p>}
      {nodes.length === 0 ? (
        <div className="mt-3">
          <SmallEmpty label="No embedded graph nodes" />
        </div>
      ) : (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="mt-3 h-56 w-full rounded-md bg-muted/25"
          role="img"
          aria-label={`Embedded graph ${artifact.title}`}
        >
          {links.map((link, index) => {
            const source = positions.get(link.source)
            const target = positions.get(link.target)
            if (!source || !target) return null
            return (
              <line
                key={`${link.source}-${link.target}-${index}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="currentColor"
                strokeOpacity="0.2"
                strokeWidth="1.4"
                className="text-muted-foreground"
              />
            )
          })}
          {nodes.map((node) => {
            const position = positions.get(node.key) ?? { x: centerX, y: centerY }
            const shortLabel = node.label.length > 22 ? `${node.label.slice(0, 20)}...` : node.label
            return (
              <g
                key={node.key}
                role="button"
                tabIndex={0}
                className="cursor-pointer outline-none"
                onClick={() => onEntitySelect(node.key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    onEntitySelect(node.key)
                  }
                }}
              >
                <circle
                  cx={position.x}
                  cy={position.y}
                  r="10"
                  fill={getNodeColor(node.type)}
                  stroke="currentColor"
                  strokeOpacity="0.2"
                  strokeWidth="1.5"
                />
                <text
                  x={position.x}
                  y={position.y + 23}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[10px]"
                >
                  {shortLabel}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </figure>
  )
}

function TableArtifact({
  artifact,
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  const columns = asArray<Dict>(artifact.data.columns)
  const rows = asArray<Dict>(artifact.data.rows)
  return (
    <ArtifactShell artifact={artifact} exportEnabled={exportEnabled}>
      {rows.length === 0 ? (
        <SmallEmpty label="No rows returned" />
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-max min-w-full border-separate border-spacing-0 text-xs">
            <thead className="sticky top-0 z-10 bg-muted/70 backdrop-blur">
              <tr>
                {columns.map((column) => (
                  <th key={valueText(column.key)} className="whitespace-nowrap border-b border-border/70 px-3 py-2 text-left font-semibold text-foreground">
                    {valueText(column.label || column.key)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => {
                const key = entityKeyFromRecord(row)
                return (
                  <tr
                    key={rowIndex}
                    onClick={() => key && onEntitySelect(key)}
                    className={cn(
                      "text-foreground",
                      key && "cursor-pointer hover:bg-muted/45"
                    )}
                  >
                    {columns.map((column) => {
                      const cellText = valueText(row[valueText(column.key)]).slice(0, 180)
                      return (
                        <td
                          key={valueText(column.key)}
                          className="max-w-80 truncate border-b border-border/50 px-3 py-2 align-top leading-5 text-muted-foreground"
                          title={cellText}
                        >
                          {cellText}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </ArtifactShell>
  )
}

function MapArtifact({
  artifact,
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  const locations = asArray<Dict>(artifact.data.locations)
  const coords = locations
    .map((location) => ({
      raw: location,
      latitude: Number(location.latitude),
      longitude: Number(location.longitude),
    }))
    .filter((location) => Number.isFinite(location.latitude) && Number.isFinite(location.longitude))

  const minLat = Math.min(...coords.map((location) => location.latitude), 0)
  const maxLat = Math.max(...coords.map((location) => location.latitude), 1)
  const minLng = Math.min(...coords.map((location) => location.longitude), 0)
  const maxLng = Math.max(...coords.map((location) => location.longitude), 1)
  const latSpan = Math.max(maxLat - minLat, 0.001)
  const lngSpan = Math.max(maxLng - minLng, 0.001)

  return (
    <ArtifactShell artifact={artifact} exportEnabled={exportEnabled}>
      <div className="relative min-h-[320px] flex-1 overflow-hidden rounded-md border border-border bg-slate-950">
        <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,.18)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.18)_1px,transparent_1px)] [background-size:32px_32px]" />
        {coords.map((location, index) => {
          const left = ((location.longitude - minLng) / lngSpan) * 86 + 7
          const top = 93 - ((location.latitude - minLat) / latSpan) * 86
          const key = entityKeyFromRecord(location.raw)
          return (
            <button
              key={valueText(location.raw.key || index)}
              type="button"
              className="absolute size-3 rounded-full bg-amber-400 shadow-[0_0_0_4px_rgba(251,191,36,.2)] outline-none ring-offset-2 ring-offset-slate-950 transition-transform hover:scale-125 focus-visible:ring-2 focus-visible:ring-amber-300"
              style={{ left: `${left}%`, top: `${top}%` }}
              title={valueText(location.raw.name || location.raw.key)}
              onClick={() => key && onEntitySelect(key)}
            />
          )
        })}
      </div>
      <div className="mt-3 grid max-h-44 shrink-0 grid-cols-1 gap-2 overflow-y-auto pr-1">
        {locations.slice(0, 5).map((location, index) => {
          const key = entityKeyFromRecord(location)
          return (
            <button
              key={valueText(location.key || index)}
              type="button"
              onClick={() => key && onEntitySelect(key)}
              className={cn(
                "rounded-md border border-border px-3 py-2 text-left text-xs",
                key && "hover:border-amber-400/70 hover:bg-amber-50/40 dark:hover:bg-amber-500/10"
              )}
            >
              <div className="font-medium text-foreground">
                {valueText(location.name || location.key || "Unnamed location")}
              </div>
              <div className="mt-0.5 text-muted-foreground">
                {valueText(location.latitude)}, {valueText(location.longitude)}
              </div>
            </button>
          )
        })}
      </div>
    </ArtifactShell>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold text-foreground">
        {value}
      </div>
    </div>
  )
}

function SmallEmpty({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
      {label}
    </div>
  )
}
