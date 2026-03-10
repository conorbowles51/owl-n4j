import { useState, useRef, useCallback, useEffect } from "react"
import { Send, Sparkles, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { useGraphStore } from "@/stores/graph.store"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { EntityType } from "@/lib/theme"
import { llmConfigAPI } from "@/features/evidence/api"
import type { LLMModel } from "@/types/evidence.types"

interface ContextNode {
  key: string
  label: string
  type: EntityType
}

interface ChatInputProps {
  onSend: (message: string, model?: string, provider?: string) => void
  isLoading: boolean
  contextNodes: ContextNode[]
  contextDocument?: string | null
  suggestions: string[]
}

const DEFAULT_MODEL = "gpt-4o"
const DEFAULT_PROVIDER = "openai"

export function ChatInput({
  onSend,
  isLoading,
  contextNodes,
  contextDocument,
  suggestions,
}: ChatInputProps) {
  const [input, setInput] = useState("")
  const [models, setModels] = useState<LLMModel[]>([])
  const [selectedModelId, setSelectedModelId] = useState(DEFAULT_MODEL)
  const [selectedProvider, setSelectedProvider] = useState(DEFAULT_PROVIDER)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const modelsLoaded = useRef(false)

  // Load models once
  useEffect(() => {
    if (modelsLoaded.current) return
    modelsLoaded.current = true
    llmConfigAPI
      .getModels()
      .then((res) => {
        const list = res.models ?? []
        setModels(list)
        if (list.length > 0 && !list.some((m) => m.id === DEFAULT_MODEL)) {
          setSelectedModelId(list[0].id)
          setSelectedProvider(list[0].provider)
        }
      })
      .catch(() => {})
  }, [])

  const handleModelSelect = (modelId: string) => {
    const model = models.find((m) => m.id === modelId)
    if (model) {
      setSelectedModelId(model.id)
      setSelectedProvider(model.provider)
    }
  }

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed, selectedModelId, selectedProvider)
    setInput("")
  }, [input, isLoading, onSend, selectedModelId, selectedProvider])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="border-t border-border">
      {/* Context badges */}
      {(contextNodes.length > 0 || contextDocument) && (
        <div className="flex flex-wrap items-center gap-1 px-4 pt-2">
          {contextNodes.length > 0 && (
            <Button
              variant="ghost"
              size="icon-sm"
              className="size-5 shrink-0 text-muted-foreground hover:text-foreground"
              onClick={() => useGraphStore.getState().clearSelection()}
              title="Deselect all entities"
            >
              <XCircle className="size-3.5" />
            </Button>
          )}
          {contextNodes.map((node) => (
            <Badge key={node.key} variant="outline" className="gap-1 py-0.5">
              <NodeBadge type={node.type} />
              <span className="max-w-[100px] truncate text-[10px]">
                {node.label}
              </span>
            </Badge>
          ))}
          {contextDocument && (
            <Badge variant="amber" className="text-[10px]">
              Scoped: {contextDocument}
            </Badge>
          )}
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && input === "" && (
        <div className="flex flex-wrap gap-1 px-4 pt-2">
          {suggestions.slice(0, 3).map((s, i) => (
            <button
              key={i}
              onClick={() => {
                setInput(s)
                textareaRef.current?.focus()
              }}
              className="rounded-full border border-border px-2.5 py-1 text-[10px] text-muted-foreground transition hover:border-amber-500/50 hover:text-foreground"
            >
              <Sparkles className="mr-1 inline size-2.5 text-amber-500" />
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="flex items-end gap-2 p-4">
        {/* Model selector */}
        {models.length > 0 && (
          <Select value={selectedModelId} onValueChange={handleModelSelect}>
            <SelectTrigger className="h-[40px] w-[130px] shrink-0 text-xs">
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
        )}

        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your case..."
          className="min-h-[40px] max-h-[160px] resize-none"
          rows={1}
        />
        <Button
          variant="primary"
          size="icon-sm"
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
          className="shrink-0"
        >
          <Send className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}
