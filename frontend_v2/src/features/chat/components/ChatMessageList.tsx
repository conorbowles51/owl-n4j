import { useRef, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ChatWaitingLine } from "./ChatWaitingLine"
import { Skeleton } from "@/components/ui/skeleton"
import { ChatMessage } from "./ChatMessage"
import { WithCitations } from "@/components/citations/citations"
import type { ChatMessageData } from "../types"

interface ChatMessageListProps {
  messages: ChatMessageData[]
  isStreaming: boolean
}

export function ChatMessageList({
  messages,
  isStreaming,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <WithCitations>
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-3xl space-y-4 p-4">
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {isStreaming && (
          <div className="space-y-2 rounded-lg bg-muted/30 p-4">
            <ChatWaitingLine />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
    </WithCitations>
  )
}
