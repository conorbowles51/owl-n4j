import { useState, useRef, useCallback } from "react"
import { Send, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import type { EntityType } from "@/lib/theme"

interface ContextNode {
  key: string
  label: string
  type: EntityType
}

interface ChatInputProps {
  onSend: (message: string) => void
  isLoading: boolean
  contextNodes: ContextNode[]
  contextDocument?: string | null
  suggestions: string[]
}

export function ChatInput({
  onSend,
  isLoading,
  contextNodes,
  contextDocument,
  suggestions,
}: ChatInputProps) {
  const [input, setInput] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed)
    setInput("")
  }, [input, isLoading, onSend])

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
