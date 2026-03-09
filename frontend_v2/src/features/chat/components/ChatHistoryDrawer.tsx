import { MessageSquare, Clock } from "lucide-react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { ScrollArea } from "@/components/ui/scroll-area"
import { EmptyState } from "@/components/ui/empty-state"

export interface ConversationSummary {
  id: string
  title: string
  messageCount: number
  lastMessageAt: string
}

interface ChatHistoryDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  history: ConversationSummary[]
  onSelectConversation: (id: string) => void
}

export function ChatHistoryDrawer({
  open,
  onOpenChange,
  history,
  onSelectConversation,
}: ChatHistoryDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-80 p-0">
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="flex items-center gap-2 text-sm">
            <Clock className="size-4" />
            Chat History
          </SheetTitle>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-60px)]">
          {history.length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title="No conversations"
              description="Start chatting to build history"
              className="py-12"
            />
          ) : (
            <div className="p-2">
              {history.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => {
                    onSelectConversation(conv.id)
                    onOpenChange(false)
                  }}
                  className="flex w-full items-start gap-2 rounded-md px-3 py-2 text-left hover:bg-muted"
                >
                  <MessageSquare className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium">
                      {conv.title}
                    </p>
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                      <span>{conv.messageCount} messages</span>
                      <span>
                        {new Date(conv.lastMessageAt).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
