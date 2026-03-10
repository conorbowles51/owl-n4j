import { useState } from "react"
import { useParams } from "react-router-dom"
import { MessageSquare } from "lucide-react"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { EmptyState } from "@/components/ui/empty-state"
import { ChatMessageList } from "./ChatMessageList"
import { ChatInput } from "./ChatInput"
import { ChatHeader } from "./ChatHeader"
import { ConversationSidebar } from "./ConversationSidebar"
import { ResultGraphPanel } from "./ResultGraphPanel"
import { CitationPanel } from "./CitationPanel"
import { useChat } from "../hooks/use-chat"
import { useChatContext } from "../hooks/use-chat-context"
import { useChatStore } from "../stores/chat.store"

export function ChatPage() {
  const { id: caseId } = useParams()
  const [citationFile, setCitationFile] = useState<string | null>(null)
  const chat = useChat(caseId!)
  const context = useChatContext(caseId!)
  const resultGraphPanelOpen = useChatStore((s) => s.resultGraphPanelOpen)

  return (
    <div className="flex h-full">
      {/* Left: Conversation sidebar */}
      <ConversationSidebar
        caseId={caseId!}
        onNewChat={chat.startNewConversation}
        onSelectConversation={chat.loadConversation}
      />

      {/* Center + Right: Resizable split between chat and result graph */}
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        {/* Chat messages + input */}
        <ResizablePanel
          id="chat-messages"
          order={1}
          defaultSize={resultGraphPanelOpen ? "55" : "100"}
          minSize="30"
        >
          <div className="flex h-full flex-col min-w-0">
            <ChatHeader caseId={caseId!} />

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

          {/* Citation panel (overlays on right of chat area) */}
          {citationFile && (
            <CitationPanel
              filename={citationFile}
              onClose={() => setCitationFile(null)}
            />
          )}
        </ResizablePanel>

        {/* Result graph — resizable right panel */}
        {resultGraphPanelOpen && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel
              id="chat-result-graph"
              order={2}
              defaultSize="45"
              minSize="20"
              maxSize="60"
            >
              <ResultGraphPanel />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>

      {/* Collapsed rail when result graph is hidden */}
      {!resultGraphPanelOpen && <ResultGraphPanel />}
    </div>
  )
}
