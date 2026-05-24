import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { MouseEvent, MutableRefObject, ReactNode } from "react"
import { useParams } from "react-router-dom"
import ForceGraph2D, {
  type ForceGraphMethods,
  type LinkObject,
  type NodeObject,
} from "react-force-graph-2d"
import {
  Bot,
  Clock3,
  Coins,
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
import type {
  AgentArtifact,
  AgentClientMessage,
  AgentStoredMessage,
  AgentThreadSummary,
  AgentToolTraceItem,
} from "../types"

type Dict = Record<string, unknown>

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

const artifactIcons = {
  graph: Network,
  timeline: Clock3,
  table: Table2,
  map: MapIcon,
  financial: Coins,
} as const

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

function entityKeyFromRecord(value: Dict): string | null {
  for (const key of ["key", "entity_key", "node_key", "target_key", "source_key"]) {
    const candidate = value[key]
    if (typeof candidate === "string" && candidate.trim()) return candidate
  }
  return null
}

function stopAndSelect(
  event: MouseEvent,
  key: string | null,
  onEntitySelect: (key: string) => void
) {
  event.stopPropagation()
  if (key) onEntitySelect(key)
}

function compactText(value: unknown, fallback = "") {
  const text = valueText(value || fallback)
  return text.length > 220 ? `${text.slice(0, 217)}...` : text
}

function formatAmount(value: unknown, currency?: unknown) {
  const amount = Number(value)
  const currencyText = valueText(currency)
  if (!Number.isFinite(amount)) return valueText(value)
  const formatted = new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
  }).format(amount)
  return currencyText ? `${formatted} ${currencyText}` : formatted
}

function storedToClientMessage(message: AgentStoredMessage): AgentClientMessage | null {
  if (message.role !== "user" && message.role !== "assistant") return null
  return {
    id: message.id,
    role: message.role,
    content: message.content,
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

function artifactFilename(artifact: AgentArtifact, format: "csv") {
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
  if (artifact.type === "timeline") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.events)[0] ?? {})
  }
  if (artifact.type === "financial") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.transactions)[0] ?? {})
  }
  if (artifact.type === "map") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.locations)[0] ?? {})
  }
  if (artifact.type === "table") {
    return entityKeyFromRecord(asArray<Dict>(artifact.data.rows)[0] ?? {})
  }
  return null
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
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null)
  const [detailsPanelOpen, setDetailsPanelOpen] = useState(false)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)

  const selectedArtifact = useMemo(
    () => artifacts.find((artifact) => artifact.id === selectedArtifactId) ?? artifacts[0] ?? null,
    [artifacts, selectedArtifactId]
  )

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
    setSelectedArtifactId(null)
    setInput("")
    setRunStatusText(null)
    setActiveRunId(null)
  }

  const sendMessage = async () => {
    const prompt = input.trim()
    if (!prompt || !caseId || isLoading) return

    const optimisticId = `local_${Date.now()}`
    let committedUserMessageId = optimisticId
    setInput("")
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
                createdAt: response.created_at,
              },
            ])
            setArtifacts(response.artifacts)
            setToolTrace(response.tool_trace)
            setSelectedArtifactId(response.artifacts[0]?.id ?? null)
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
      setMessages((current) =>
        current.filter(
          (message) =>
            message.id !== optimisticId && message.id !== committedUserMessageId
        )
      )
      const message = error instanceof Error ? error.message : "Agent request failed"
      toast.error(message)
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
                <Badge variant="secondary" className="hidden sm:inline-flex">
                  gpt-5-mini
                </Badge>
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
                <div className="mx-auto flex max-w-3xl flex-col gap-4">
                  {messages.map((message) => (
                    <MessageBubble key={message.id} message={message} />
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

            {toolTrace.length > 0 && (
              <ToolTrace trace={toolTrace} />
            )}

            <div className="border-t border-border bg-background p-4">
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
                <Button size="icon" onClick={sendMessage} disabled={!input.trim() || isLoading} aria-label="Send agent prompt">
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

function MessageBubble({ message }: { message: AgentClientMessage }) {
  const isUser = message.role === "user"
  return (
    <article className={cn("flex gap-3", isUser && "justify-end")}>
      {!isUser && (
        <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Bot className="size-4" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[84%] rounded-lg border px-3 py-2 text-sm",
          isUser
            ? "border-primary/15 bg-primary text-primary-foreground"
            : "border-border bg-card text-card-foreground"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <Markdown content={message.content} className="text-sm leading-6" />
        )}
        <div className={cn("mt-1 text-[11px]", isUser ? "text-primary-foreground/70" : "text-muted-foreground")}>
          {message.pending ? "Sending..." : formatTime(message.createdAt)}
        </div>
      </div>
    </article>
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
              Click graph nodes, timeline items, map points, or financial entities.
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
    <section className="flex h-full min-w-0 flex-col border-l border-border bg-muted/10">
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
              Ask for a graph, timeline, map, table, or financial view.
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
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {selectedArtifact && (
              <ArtifactRenderer
                artifact={selectedArtifact}
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
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  if (artifact.type === "graph") return <GraphArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "timeline") return <TimelineArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "table") return <TableArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "map") return <MapArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  if (artifact.type === "financial") return <FinancialArtifact artifact={artifact} exportEnabled={exportEnabled} onEntitySelect={onEntitySelect} />
  return <pre className="text-xs">{JSON.stringify(artifact.data, null, 2)}</pre>
}

function ArtifactShell({
  artifact,
  children,
  exportEnabled,
}: {
  artifact: AgentArtifact
  children: ReactNode
  exportEnabled: boolean
}) {
  const Icon = artifactIcons[artifact.type] ?? FileText
  const [isDownloading, setIsDownloading] = useState(false)

  const downloadCsv = async () => {
    if (!exportEnabled || isDownloading) return
    setIsDownloading(true)
    try {
      await downloadProtectedFile(
        agentAPI.artifactExportUrl(artifact.id, "csv"),
        artifactFilename(artifact, "csv")
      )
      toast.success("CSV export downloaded")
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to download CSV"
      toast.error(message)
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-background">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="size-4 text-muted-foreground" />
          <h3 className="truncate text-sm font-semibold text-foreground">
            {artifact.title}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={downloadCsv}
            disabled={!exportEnabled || isDownloading}
            title={exportEnabled ? "Download CSV" : "CSV is available when the run finishes"}
          >
            {isDownloading ? (
              <Loader2 className="mr-1 size-3 animate-spin" />
            ) : (
              <Download className="mr-1 size-3" />
            )}
            CSV
          </Button>
          <Badge variant="secondary" className="capitalize">
            {artifact.type}
          </Badge>
        </div>
      </div>
      <div className="p-3">{children}</div>
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
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
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

  useEffect(() => {
    if (graphData.nodes.length === 0) return
    window.setTimeout(() => graphRef.current?.zoomToFit(450, 42), 120)
  }, [graphData.nodes.length, graphData.links.length])

  const paintNode = useCallback(
    (node: AgentForceNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x ?? 0
      const y = node.y ?? 0
      const isSelected = selectedNodeKeys.has(node.key)
      const radius = 5 + Math.min((node._degree ?? 0) * 1.2, 9)

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

      const fontSize = Math.max(10 / globalScale, 2.5)
      ctx.font = `${fontSize}px Inter, system-ui, sans-serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "top"
      ctx.fillStyle = canvasColors.labelText
      const label = node.label.length > 26 ? `${node.label.slice(0, 24)}...` : node.label
      ctx.fillText(label, x, y + radius + 3)
    },
    [canvasColors, selectedNodeKeys]
  )

  const paintLink = useCallback(
    (link: AgentForceLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const source = link.source as AgentForceNode
      const target = link.target as AgentForceNode
      if (source?.x == null || source.y == null || target?.x == null || target.y == null) return

      ctx.beginPath()
      ctx.moveTo(source.x, source.y)
      ctx.lineTo(target.x, target.y)
      ctx.strokeStyle = canvasColors.linkColor
      ctx.globalAlpha = 0.45
      ctx.lineWidth = Math.max(1 / Math.sqrt(globalScale), 0.6)
      ctx.stroke()

      const dx = target.x - source.x
      const dy = target.y - source.y
      const length = Math.sqrt(dx * dx + dy * dy)
      if (length > 1) {
        const angle = Math.atan2(dy, dx)
        const arrowLen = 5 / globalScale
        const endX = target.x - (dx / length) * 10
        const endY = target.y - (dy / length) * 10
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

      if (link.type) {
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

      ctx.globalAlpha = 1
    },
    [canvasColors]
  )

  return (
    <ArtifactShell artifact={artifact} exportEnabled={exportEnabled}>
      <div ref={containerRef} className="h-[440px] overflow-hidden rounded-md border border-border bg-slate-100 dark:bg-slate-950">
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
              const radius = 6 + Math.min((node._degree ?? 0) * 1.2, 9)
              ctx.beginPath()
              ctx.arc(node.x ?? 0, node.y ?? 0, radius + 5, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()
            }}
            linkCanvasObject={paintLink}
            linkDirectionalParticles={0}
            onNodeClick={(node) => onEntitySelect(node.key)}
            cooldownTime={1800}
            d3AlphaDecay={0.035}
            d3VelocityDecay={0.36}
          />
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <Stat label="Nodes" value={graphData.nodes.length} />
        <Stat label="Relationships" value={graphData.links.length} />
      </div>
    </ArtifactShell>
  )
}

function TimelineArtifact({
  artifact,
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  const events = asArray<Dict>(artifact.data.events)
  return (
    <ArtifactShell artifact={artifact} exportEnabled={exportEnabled}>
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
        <Stat label="Events" value={events.length} />
        <Stat label="Range" value={`${valueText(events[0]?.date || "n/a")} - ${valueText(events[events.length - 1]?.date || "n/a")}`} />
      </div>
      <div className="space-y-2">
        {events.length === 0 ? (
          <SmallEmpty label="No timeline events returned" />
        ) : (
          <div className="relative pl-5">
            <div className="absolute bottom-2 left-[5px] top-2 w-px bg-border" />
            {events.map((event, index) => {
              const key = entityKeyFromRecord(event)
              const clickable = Boolean(key)
              return (
                <button
                  key={valueText(event.key || index)}
                  type="button"
                  onClick={() => key && onEntitySelect(key)}
                  className={cn(
                    "group relative mb-2 w-full rounded-md border border-border bg-card px-3 py-2 text-left transition-colors",
                    clickable && "hover:border-amber-400/70 hover:bg-amber-50/40 dark:hover:bg-amber-500/10"
                  )}
                >
                  <span className="absolute -left-[21px] top-3 size-3 rounded-full border-2 border-background bg-amber-500 shadow-sm" />
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                          {valueText(event.date || "No date")}
                          {event.time ? ` ${valueText(event.time)}` : ""}
                        </span>
                        {typeof event.type === "string" && event.type && (
                          <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                            {valueText(event.type)}
                          </Badge>
                        )}
                      </div>
                      <div className="mt-1 text-sm font-semibold text-foreground">
                        {valueText(event.name || event.key || "Untitled event")}
                      </div>
                      <p className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">
                        {compactText(event.summary || event.notes)}
                      </p>
                    </div>
                    {clickable && (
                      <PanelRightOpen className="mt-1 size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </ArtifactShell>
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
        <div className="max-h-[520px] overflow-auto rounded-md border border-border">
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 bg-muted">
              <tr>
                {columns.map((column) => (
                  <th key={valueText(column.key)} className="border-b border-border px-2 py-2 text-left font-semibold">
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
                      "odd:bg-muted/30",
                      key && "cursor-pointer hover:bg-amber-50/50 dark:hover:bg-amber-500/10"
                    )}
                  >
                    {columns.map((column) => (
                      <td key={valueText(column.key)} className="border-b border-border px-2 py-2 align-top">
                        {valueText(row[valueText(column.key)]).slice(0, 180)}
                      </td>
                    ))}
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
      <div className="relative h-80 overflow-hidden rounded-md border border-border bg-slate-950">
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
      <div className="mt-3 grid grid-cols-1 gap-2">
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

function FinancialArtifact({
  artifact,
  exportEnabled,
  onEntitySelect,
}: {
  artifact: AgentArtifact
  exportEnabled: boolean
  onEntitySelect: (key: string) => void
}) {
  const transactions = asArray<Dict>(artifact.data.transactions)
  const totalVolume = artifact.data.total_volume || transactions.reduce((sum, transaction) => {
    const amount = Number(transaction.amount)
    return Number.isFinite(amount) ? sum + Math.abs(amount) : sum
  }, 0)
  return (
    <ArtifactShell artifact={artifact} exportEnabled={exportEnabled}>
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
        <Stat label="Transactions" value={transactions.length} />
        <Stat label="Volume" value={formatAmount(totalVolume)} />
      </div>
      {transactions.length === 0 ? (
        <SmallEmpty label="No financial records returned" />
      ) : (
        <div className="space-y-2">
          {transactions.slice(0, 12).map((transaction, index) => {
            const fromEntity = asRecord(transaction.from_entity)
            const toEntity = asRecord(transaction.to_entity)
            const transactionKey = entityKeyFromRecord(transaction)
            const fromKey = entityKeyFromRecord(fromEntity)
            const toKey = entityKeyFromRecord(toEntity)
            return (
              <div
                key={valueText(transaction.key || index)}
                role={transactionKey ? "button" : undefined}
                tabIndex={transactionKey ? 0 : undefined}
                onClick={() => transactionKey && onEntitySelect(transactionKey)}
                onKeyDown={(event) => {
                  if (!transactionKey) return
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    onEntitySelect(transactionKey)
                  }
                }}
                className={cn(
                  "w-full rounded-md border border-border bg-card p-3 text-left text-xs transition-colors",
                  transactionKey && "hover:border-amber-400/70 hover:bg-amber-50/40 dark:hover:bg-amber-500/10"
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {valueText(transaction.date || "No date")}
                      </span>
                      {typeof transaction.category === "string" && transaction.category && (
                        <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                          {valueText(transaction.category)}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-1 truncate text-sm font-semibold text-foreground">
                      {valueText(transaction.name || transaction.key || "Financial record")}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-sm font-semibold text-foreground">
                      {formatAmount(transaction.amount, transaction.currency)}
                    </div>
                    {typeof transaction.type === "string" && transaction.type && (
                      <div className="text-[11px] text-muted-foreground">
                        {valueText(transaction.type)}
                      </div>
                    )}
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-2 text-muted-foreground">
                  <EntityChip
                    label={valueText(fromEntity.name || fromEntity.key || transaction.from_entity || "Unknown sender")}
                    entityKey={fromKey}
                    onEntitySelect={onEntitySelect}
                  />
                  <span className="text-border">{"->"}</span>
                  <EntityChip
                    label={valueText(toEntity.name || toEntity.key || transaction.to_entity || "Unknown receiver")}
                    entityKey={toKey}
                    onEntitySelect={onEntitySelect}
                  />
                </div>
                {Boolean(transaction.summary || transaction.purpose || transaction.notes) && (
                  <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                    {compactText(transaction.summary || transaction.purpose || transaction.notes)}
                  </p>
                )}
              </div>
            )
          })}
          {transactions.length > 12 && (
            <div className="rounded-md border border-dashed border-border p-2 text-center text-xs text-muted-foreground">
              Showing 12 of {transactions.length} records. Download CSV for the full artifact.
            </div>
          )}
        </div>
      )}
    </ArtifactShell>
  )
}

function EntityChip({
  label,
  entityKey,
  onEntitySelect,
}: {
  label: string
  entityKey: string | null
  onEntitySelect: (key: string) => void
}) {
  return (
    <span
      role={entityKey ? "button" : undefined}
      tabIndex={entityKey ? 0 : undefined}
      onClick={(event) => stopAndSelect(event, entityKey, onEntitySelect)}
      onKeyDown={(event) => {
        if (!entityKey) return
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault()
          onEntitySelect(entityKey)
        }
      }}
      className={cn(
        "min-w-0 max-w-[45%] truncate rounded border border-border bg-muted/40 px-2 py-1 text-[11px]",
        entityKey && "cursor-pointer hover:border-amber-400/70 hover:bg-amber-50 dark:hover:bg-amber-500/10"
      )}
      title={label}
    >
      {label}
    </span>
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
