import { useRef, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { ChatMessage } from "./ChatMessage"
import type { ChatMessageData } from "../types"

interface ChatMessageListProps {
  messages: ChatMessageData[]
  isStreaming: boolean
  onCitationClick?: (filename: string) => void
}

export function ChatMessageList({
  messages,
  isStreaming,
  onCitationClick,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-3xl space-y-4 p-4">
        {messages.map((msg, i) => (
          <ChatMessage
            key={i}
            message={msg}
            onCitationClick={onCitationClick}
          />
        ))}
        {isStreaming && (
          <div className="space-y-2 rounded-lg bg-muted/30 p-4">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
