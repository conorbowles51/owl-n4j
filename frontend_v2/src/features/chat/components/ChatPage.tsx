import { useState } from "react"
import { useParams } from "react-router-dom"
import { MessageSquare, History } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { ChatMessageList } from "./ChatMessageList"
import { ChatInput } from "./ChatInput"
import { ChatHistoryDrawer } from "./ChatHistoryDrawer"
import { CitationPanel } from "./CitationPanel"
import { useChat } from "../hooks/use-chat"
import { useChatContext } from "../hooks/use-chat-context"

export function ChatPage() {
  const { id: caseId } = useParams()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [citationFile, setCitationFile] = useState<string | null>(null)
  const chat = useChat(caseId!)
  const context = useChatContext(caseId!)

  return (
    <div className="flex h-full">
      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-2">
          <MessageSquare className="size-4 text-amber-500" />
          <span className="text-sm font-semibold">AI Assistant</span>
          <div className="flex-1" />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setHistoryOpen(true)}
          >
            <History className="size-3.5" />
            History
          </Button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-hidden">
          {chat.messages.length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title="Start a conversation"
              description="Ask questions about your case data. Select nodes for focused context."
              className="h-full"
            />
          ) : (
            <ChatMessageList
              messages={chat.messages}
              isStreaming={chat.isLoading}
              onCitationClick={(filename) => setCitationFile(filename)}
            />
          )}
        </div>

        {/* Input */}
        <ChatInput
          onSend={chat.sendMessage}
          isLoading={chat.isLoading}
          contextNodes={context.selectedNodes}
          contextDocument={context.scopedDocument}
          suggestions={chat.suggestions}
        />
      </div>

      {/* Citation panel */}
      {citationFile && (
        <CitationPanel
          filename={citationFile}
          onClose={() => setCitationFile(null)}
        />
      )}

      {/* History drawer */}
      <ChatHistoryDrawer
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        history={chat.history}
        onSelectConversation={chat.loadConversation}
      />
    </div>
  )
}
