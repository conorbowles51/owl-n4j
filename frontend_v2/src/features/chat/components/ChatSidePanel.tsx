import { useRef, useEffect, useState, useMemo, type KeyboardEvent } from "react"
import { Send, Bot } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ChatMessage } from "./ChatMessage"
import { cn } from "@/lib/cn"
import { useQuickChat } from "../hooks/use-quick-chat"
import { useGraphStore } from "@/stores/graph.store"
import { evidenceAPI, llmConfigAPI } from "@/features/evidence/api"
import type { LLMModel } from "@/types/evidence.types"

const DEFAULT_MODEL = "gpt-4o"
const DEFAULT_PROVIDER = "openai"

type ContextMode = "full" | "selection"

interface ChatSidePanelProps {
  caseId: string
}

export function ChatSidePanel({ caseId }: ChatSidePanelProps) {
  const [models, setModels] = useState<LLMModel[]>([])
  const [selectedModelId, setSelectedModelId] = useState(DEFAULT_MODEL)
  const [selectedProvider, setSelectedProvider] = useState(DEFAULT_PROVIDER)
  const [contextMode, setContextMode] = useState<ContextMode>("full")
  const [input, setInput] = useState("")
  const [viewerDoc, setViewerDoc] = useState<{
    url: string
    name: string
    page?: number
  } | null>(null)
  const modelsLoaded = useRef(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const selectedKeysArray = useMemo(
    () => (contextMode === "selection" ? Array.from(selectedNodeKeys) : undefined),
    [contextMode, selectedNodeKeys]
  )

  // Load available models once
  useEffect(() => {
    if (modelsLoaded.current) return
    modelsLoaded.current = true
    llmConfigAPI.getModels().then((res) => {
      const list = res.models ?? []
      setModels(list)
      if (list.length > 0 && !list.some((m) => m.id === DEFAULT_MODEL)) {
        setSelectedModelId(list[0].id)
        setSelectedProvider(list[0].provider)
      }
    }).catch(() => {})
  }, [])

  const { messages, isLoading, sendMessage, clearMessages } = useQuickChat({
    caseId,
    model: selectedModelId,
    provider: selectedProvider,
    selectedKeys: selectedKeysArray,
    scope: contextMode === "selection" ? "selection" : "case_overview",
  })

  // Clear messages on case changes.
  useEffect(() => {
    clearMessages()
  }, [caseId, clearMessages])

  // Auto-focus textarea on mount
  useEffect(() => {
    setTimeout(() => textareaRef.current?.focus(), 100)
  }, [])

  // Auto-scroll on new messages
  useEffect(() => {
    const viewport = scrollRef.current?.querySelector<HTMLElement>(
      '[data-slot="scroll-area-viewport"]'
    )
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [messages, isLoading])

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return
    sendMessage(trimmed)
    setInput("")
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleModelSelect = (modelId: string) => {
    const model = models.find((m) => m.id === modelId)
    if (model) {
      setSelectedModelId(model.id)
      setSelectedProvider(model.provider)
    }
  }

  const openDocument = async (filename: string, page?: number) => {
    try {
      const result = await evidenceAPI.findByFilename(filename, caseId)
      if (!result.found || !result.evidence_id) {
        toast.error("Source file not found")
        return
      }

      setViewerDoc({
        url: evidenceAPI.getFileUrl(result.evidence_id),
        name: filename,
        page,
      })
    } catch {
      toast.error("Failed to load source file")
    }
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Model selector */}
      {models.length > 0 && (
        <div className="flex items-center border-b px-4 py-1.5">
          <Select value={selectedModelId} onValueChange={handleModelSelect}>
            <SelectTrigger className="h-7 w-[140px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {models.map((m) => (
                <SelectItem key={m.id} value={m.id} className="text-xs">
                  {m.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Context mode toggle */}
      <div className="flex items-center gap-1.5 border-b px-4 py-1.5">
        <div className="flex rounded-md border border-border bg-muted/50 p-0.5">
          <button
            type="button"
            className={cn(
              "rounded px-2.5 py-1 text-xs font-medium transition-colors",
              contextMode === "full"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setContextMode("full")}
          >
            Case Overview
          </button>
          <button
            type="button"
            className={cn(
              "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors",
              contextMode === "selection"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setContextMode("selection")}
          >
            Selection
            {contextMode === "selection" && selectedNodeKeys.size > 0 && (
              <span className="inline-flex size-4 items-center justify-center rounded-full bg-amber-500 text-[10px] font-bold text-white">
                {selectedNodeKeys.size}
              </span>
            )}
          </button>
        </div>
        {contextMode === "selection" && selectedNodeKeys.size === 0 && (
          <span className="text-xs text-amber-600 dark:text-amber-400">
            Select nodes on the graph
          </span>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="p-2">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Bot className="size-8 text-amber-500/50 mb-3" />
              <p className="text-sm font-medium text-muted-foreground">
                Ask anything about this case
              </p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                Questions are answered using your uploaded evidence
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {messages.map((msg, i) => (
                <ChatMessage
                  key={i}
                  message={msg}
                  onDocumentClick={openDocument}
                />
              ))}
              {isLoading && (
                <div className="flex items-start gap-3 rounded-lg px-4 py-3">
                  <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-amber-500/10">
                    <Bot className="size-3.5 text-amber-500" />
                  </div>
                  <div className="flex items-center gap-1 pt-1">
                    <span className="size-1.5 rounded-full bg-amber-500 animate-bounce [animation-delay:0ms]" />
                    <span className="size-1.5 rounded-full bg-amber-500 animate-bounce [animation-delay:150ms]" />
                    <span className="size-1.5 rounded-full bg-amber-500 animate-bounce [animation-delay:300ms]" />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-3">
        <div className="flex items-end gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            className="min-h-[36px] max-h-[80px] resize-none text-sm"
            rows={1}
          />
          <Button
            size="icon"
            className="size-9 shrink-0 bg-amber-500 hover:bg-amber-600 text-white"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
          >
            <Send className="size-4" />
          </Button>
        </div>
      </div>

      <DocumentViewer
        open={!!viewerDoc}
        onOpenChange={(open) => {
          if (!open) setViewerDoc(null)
        }}
        documentUrl={viewerDoc?.url}
        documentName={viewerDoc?.name}
        initialPage={viewerDoc?.page}
      />
    </div>
  )
}
