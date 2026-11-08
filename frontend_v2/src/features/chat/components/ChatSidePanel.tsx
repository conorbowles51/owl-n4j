import { useRef, useEffect, useState, type KeyboardEvent } from "react"
import { useLocation } from "react-router-dom"
import { Send, Bot, MessageSquare, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import { ChatWaitingLine } from "./ChatWaitingLine"
import { ChatMessage } from "./ChatMessage"
import { cn } from "@/lib/cn"
import { useChat } from "../hooks/use-chat"
import { useConversations } from "../hooks/use-conversations"
import { useChatStore } from "../stores/chat.store"
import { useGraphStore } from "@/stores/graph.store"
import { ActiveAIModel } from "@/features/settings/components/ActiveAIModel"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"
import { PinnedRecords } from "@/features/phones/components/PinnedRecords"

type ContextMode = "full" | "selection"

interface ChatSidePanelProps {
  caseId: string
}

export function ChatSidePanel({ caseId }: ChatSidePanelProps) {
  const location = useLocation()
  const caseLayer = useCaseLayer(caseId)
  const [contextMode, setContextMode] = useState<ContextMode>("full")
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const activeConversationId = useChatStore((s) => s.activeConversationId)
  const phoneContext = useChatStore((s) => s.phoneContext)
  const setPhoneContext = useChatStore((s) => s.setPhoneContext)
  const { data: conversations = [] } = useConversations(caseId)
  const { messages, isLoading, sendMessage, startNewConversation } = useChat(caseId)

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeConversationId
  )
  const conversationTitle =
    activeConversation?.name ??
    (activeConversationId ? "Conversation" : "New Conversation")

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
    if (
      !trimmed ||
      isLoading ||
      (contextMode === "selection" && selectedNodeKeys.size === 0)
    ) return
    const chatScope =
      caseLayer === "significant"
        ? "significant"
        : contextMode === "selection"
          ? "selection"
          : "case_overview"
    const viewContext = {
      view: location.pathname.split("/").filter(Boolean).pop() ?? "case",
      label: "Case side panel",
      route: location.pathname,
      scope: chatScope,
      selection_within_scope: contextMode === "selection",
      selections: {
        entity_keys: contextMode === "selection" ? Array.from(selectedNodeKeys) : [],
      },
      // XF-10: ids, thread and scope only; never the messages' text
      ...(phoneContext && phoneContext.caseId === caseId
        ? { phone: { thread: phoneContext.thread, thread_title: phoneContext.thread_title, scope_words: phoneContext.scope_words,
            scope_total: phoneContext.scope_total, record_ids: phoneContext.record_ids } }
        : {}),
    }
    void sendMessage(
      trimmed,
      undefined,
      undefined,
      chatScope,
      viewContext
    )
    setInput("")
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Conversation header */}
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <MessageSquare className="size-3.5 shrink-0 text-amber-500" />
        <span
          className="min-w-0 flex-1 truncate text-xs font-semibold"
          title={conversationTitle}
        >
          {conversationTitle}
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          title="New chat"
          onClick={() => {
            startNewConversation()
            setInput("")
          }}
        >
          <Plus className="size-3.5" />
        </Button>
      </div>

      <div className="flex items-center border-b px-4 py-1.5">
        <ActiveAIModel workload="chat" />
      </div>

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
            {caseLayer === "significant" ? "Significant Layer" : "Case Overview"}
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
                />
              ))}
              {isLoading && (
                <div className="flex items-start gap-3 rounded-lg px-4 py-3">
                  <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-amber-500/10">
                    <Bot className="size-3.5 text-amber-500" />
                  </div>
                  <ChatWaitingLine className="pt-0.5" />
                </div>
              )}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-3">
        {phoneContext && phoneContext.caseId === caseId && (
          <div role="status" data-testid="chat-phone-context" className="mb-2 flex items-start gap-2 rounded border bg-muted/40 px-2 py-1 text-xs">
            <span className="min-w-0 flex-1">
              Asking about {phoneContext.record_ids.length.toLocaleString("en-US")} selected {phoneContext.record_ids.length === 1 ? "message" : "messages"}
              {(phoneContext.selected_total ?? 0) > phoneContext.record_ids.length
                ? `, the ones loaded on screen of the ${phoneContext.selected_total!.toLocaleString("en-US")} selected`
                : ""}
              {phoneContext.thread_title ? ` in ${phoneContext.thread_title}` : ""}
              {phoneContext.scope_words ? ` (${phoneContext.scope_words})` : ""}.
              {phoneContext.record_ids.length > 50 ? " Only the first 50 are read with the question." : ""}
            </span>
            <button type="button" className="underline" onClick={() => setPhoneContext(null)}>Clear</button>
          </div>
        )}
        {phoneContext && phoneContext.caseId === caseId && phoneContext.record_ids.length > 0 && (
          <div className="mb-2">
            <PinnedRecords caseId={caseId} recordIds={phoneContext.record_ids} total={phoneContext.selected_total ?? undefined} />
          </div>
        )}
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
            disabled={
              !input.trim() ||
              isLoading ||
              (contextMode === "selection" && selectedNodeKeys.size === 0)
            }
          >
            <Send className="size-4" />
          </Button>
        </div>
      </div>

    </div>
  )
}
