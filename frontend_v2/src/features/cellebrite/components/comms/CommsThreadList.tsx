import { Loader2, Mail, MessageSquare, Paperclip, Phone, Smartphone } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"

import type { CommsThread } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import {
  participantSummary,
  reportLabel,
  shortDate,
  sourceAppLabel,
  threadKey,
  threadKindIcon,
} from "./commsUtils"

export function CommsThreadList({
  threads,
  loading,
  selectedThreadKey,
  reportsByKey,
  onSelect,
}: {
  threads: CommsThread[]
  loading: boolean
  selectedThreadKey: string | null
  reportsByKey: Map<string, string>
  onSelect: (thread: CommsThread) => void
}) {
  if (loading) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
        <span>Loading conversations</span>
      </div>
    )
  }

  if (threads.length === 0) {
    return <SmallEmpty label="No threads match current filters" />
  }

  return (
    <div className="h-full overflow-y-auto">
      {threads.map((thread) => {
        const key = threadKey(thread)
        return (
          <ThreadRow
            key={key}
            thread={thread}
            selected={selectedThreadKey === key}
            reportsByKey={reportsByKey}
            onSelect={() => onSelect(thread)}
          />
        )
      })}
    </div>
  )
}

function ThreadRow({
  thread,
  selected,
  reportsByKey,
  onSelect,
}: {
  thread: CommsThread
  selected: boolean
  reportsByKey: Map<string, string>
  onSelect: () => void
}) {
  const kind = threadKindIcon(thread)
  const Icon = kind === "message" ? MessageSquare : kind === "call" ? Phone : Mail
  const summary = participantSummary(thread)
  const count = thread.item_count ?? thread.message_count ?? 0
  const report = reportLabel(thread.report_key ?? thread.device_report_key, reportsByKey)
  const hasAttachments = Boolean(thread.has_attachments || thread.attachment_count)

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full border-b border-border px-3 py-2 text-left transition-colors",
        selected ? "border-l-4 border-l-amber-500 bg-amber-500/10" : "border-l-4 border-l-transparent hover:bg-muted/50"
      )}
    >
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
          <Icon className="size-3.5 text-muted-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="min-w-0 flex-1 truncate text-xs font-semibold text-foreground">
              {summary.title}
              {summary.extraCount > 0 && (
                <span className="text-muted-foreground"> +{summary.extraCount}</span>
              )}
            </span>
            <Badge variant="outline" className="shrink-0 text-[10px]">
              {thread.thread_type}
            </Badge>
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="truncate">{sourceAppLabel(thread)}</span>
            <span className="shrink-0">.</span>
            <span className="shrink-0">{shortDate(thread.last_activity)}</span>
            <span className="ml-auto shrink-0">{compactNumber(count)} items</span>
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
            {report && (
              <>
                <Smartphone className="size-3 shrink-0" />
                <span className="min-w-0 truncate">{report}</span>
              </>
            )}
            {hasAttachments && (
              <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-amber-600">
                <Paperclip className="size-3" />
                {compactNumber(Number(thread.attachment_count ?? 0) || 0)}
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  )
}

