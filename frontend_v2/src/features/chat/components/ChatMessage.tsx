import { lazy, Suspense, useState } from "react"
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
import { CitationLink, CitationScope } from "@/components/citations/citations"
import { docHrefByName, parseCitation } from "@/lib/citations"
import type { ChatMessageData } from "../types"

// Loaded when an answer is shown: the ratings code belongs to the answer, not to the first screen (bundle budget).
const AnswerRating = lazy(() =>
  import("@/features/agent/components/AnswerRating").then((m) => ({ default: m.AnswerRating })),
)

const SAVED_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

interface ChatMessageProps {
  message: ChatMessageData
  /** The case, so a saved answer can be rated. */
  caseId?: string
}

/** A source's citation: by evidence file id when the answer gave one, else by name (a shared name offers a choice). */
function sourceHref(source: { filename: string; page?: number; cite?: string }) {
  return source.cite && parseCitation(source.cite) ? source.cite : docHrefByName(source.filename, source.page)
}

export function ChatMessage({ message, caseId }: ChatMessageProps) {
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
                  <CitationScope content={message.sources.map((src) => `[s](${sourceHref(src)})`).join(" ")}>
                  {message.sources.map((src, i) => (
                    <CitationLink
                      key={i}
                      citation={parseCitation(sourceHref(src))!}
                      className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs hover:bg-muted"
                    >
                      <FileText className="size-3 text-amber-500" />
                      <span className="truncate">
                        {src.filename}
                        {src.page ? ` p.${src.page}` : ""}
                      </span>
                    </CitationLink>
                  ))}
                  </CitationScope>
                </div>
              )}
            </div>
          )}

          {/* Rating: missed something, not relevant, too thin (lx-agenttools D20) */}
          {!isUser && caseId && message.id && SAVED_ID.test(message.id) && message.content.trim() && (
            <Suspense fallback={null}>
              <AnswerRating caseId={caseId} messageId={message.id} source="chat" />
            </Suspense>
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
