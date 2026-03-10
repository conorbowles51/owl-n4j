import { MessageSquare } from "lucide-react"
import { useChatStore } from "../stores/chat.store"
import { useConversations } from "../hooks/use-conversations"

interface ChatHeaderProps {
  caseId: string
}

export function ChatHeader({ caseId }: ChatHeaderProps) {
  const activeId = useChatStore((s) => s.activeConversationId)
  const { data: conversations = [] } = useConversations()

  const activeConversation = conversations.find(
    (c) => c.id === activeId && (!c.case_id || c.case_id === caseId)
  )

  const title = activeConversation?.name || "New Conversation"

  return (
    <div className="flex items-center gap-2 border-b border-border px-4 py-2">
      <MessageSquare className="size-4 text-amber-500" />
      <span className="text-sm font-semibold truncate">{title}</span>
      <div className="flex-1" />
    </div>
  )
}
