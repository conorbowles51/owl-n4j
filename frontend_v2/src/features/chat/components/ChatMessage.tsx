import { useState } from "react"
import {
  User,
  Bot,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  Network,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { CostBadge } from "@/components/ui/cost-badge"
import { cn } from "@/lib/cn"
import { Markdown } from "@/components/ui/markdown"
import type { ChatMessageData } from "../types"

interface ChatMessageProps {
  message: ChatMessageData
  onDocumentClick?: (filename: string, page?: number) => void
}

export function ChatMessage({ message, onDocumentClick }: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const [showSources, setShowSources] = useState(false)
  const isUser = message.role === "user"

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const entityCount = message.resultGraph?.nodes?.length ?? 0

  return (
    <div
      className={cn(
        "group rounded-lg px-4 py-3",
        isUser ? "bg-muted/50" : "bg-transparent"
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex size-6 shrink-0 items-center justify-center rounded-full",
            isUser ? "bg-foreground/10" : "bg-amber-500/10"
          )}
        >
          {isUser ? (
            <User className="size-3.5 text-foreground" />
          ) : (
            <Bot className="size-3.5 text-amber-500" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold">
              {isUser ? "You" : "Assistant"}
            </span>
            {message.timestamp && (
              <span className="text-[10px] text-muted-foreground">
                {new Date(message.timestamp).toLocaleTimeString()}
              </span>
            )}
            {message.cost && message.cost.usd > 0 && (
              <CostBadge amount={message.cost.usd} />
            )}
            {message.model_info && (
              <Badge variant="outline" className="text-[10px] py-0">
                {message.model_info.model_name}
              </Badge>
            )}
          </div>

          {isUser ? (
            <div className="mt-1 text-sm leading-relaxed whitespace-pre-wrap">
              {message.content}
            </div>
          ) : (
            <Markdown
              content={message.content}
              className="mt-1 text-sm leading-relaxed"
              onOpenDocument={onDocumentClick}
            />
          )}

          {/* Result graph indicator */}
          {!isUser && entityCount > 0 && (
            <div className="mt-1.5 flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400">
              <Network className="size-3" />
              <span>{entityCount} entities found</span>
            </div>
          )}

          {/* Sources */}
          {message.sources && message.sources.length > 0 && (
            <div className="mt-2">
              <button
                onClick={() => setShowSources(!showSources)}
                className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
              >
                {showSources ? (
                  <ChevronDown className="size-3" />
                ) : (
                  <ChevronRight className="size-3" />
                )}
                {message.sources.length} source
                {message.sources.length !== 1 ? "s" : ""}
              </button>
              {showSources && (
                <div className="mt-1 space-y-1">
                  {message.sources.map((src, i) => (
                    <button
                      key={i}
                      onClick={() => onDocumentClick?.(src.filename, src.page)}
                      className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs hover:bg-muted"
                    >
                      <FileText className="size-3 text-amber-500" />
                      <span className="truncate">
                        {src.filename}
                        {src.page ? ` p.${src.page}` : ""}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Copy button */}
          {!isUser && (
            <div className="mt-2 opacity-0 transition group-hover:opacity-100">
              <Button variant="ghost" size="sm" onClick={handleCopy}>
                {copied ? (
                  <Check className="size-3" />
                ) : (
                  <Copy className="size-3" />
                )}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export type { ChatMessageData }
