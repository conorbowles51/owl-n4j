import { useState } from "react"
import { useParams } from "react-router-dom"
import { MessageSquare } from "lucide-react"
import { toast } from "sonner"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { EmptyState } from "@/components/ui/empty-state"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { ChatMessageList } from "./ChatMessageList"
import { ChatInput } from "./ChatInput"
import { ChatHeader } from "./ChatHeader"
import { ConversationSidebar } from "./ConversationSidebar"
import { ResultGraphPanel } from "./ResultGraphPanel"
import { evidenceAPI } from "@/features/evidence/api"
import { useChat } from "../hooks/use-chat"
import { useChatContext } from "../hooks/use-chat-context"
import { useChatStore } from "../stores/chat.store"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"
import { useCaseContext } from "@/features/workspace/hooks/use-workspace"
import { MandateUsageBanner } from "@/features/workspace/components/MandateUsageBanner"
import type { ChatScope } from "../types"

export function ChatPage() {
  const { id: caseId } = useParams()
  const [viewerDoc, setViewerDoc] = useState<{
    evidenceId: string
    url: string
    name: string
    page?: number
  } | null>(null)
  const chat = useChat(caseId!)
  const caseContext = useCaseContext(caseId!)
  const [mandateOverride, setMandateOverride] = useState("")
  const caseLayer = useCaseLayer(caseId)
  const context = useChatContext(caseId!)
  const resultGraphPanelOpen = useChatStore((s) => s.resultGraphPanelOpen)
  const activeOwnerId = useChatStore((s) => s.activeConversationOwnerId)
  const currentUserId = useAuthStore((s) => s.user?.id ?? null)
  const isReadOnly =
    !!activeOwnerId &&
    !!currentUserId &&
    activeOwnerId !== currentUserId

  const sendWithMandate = (
    message: string,
    model?: string,
    provider?: string,
    scope?: ChatScope,
    viewContext?: Record<string, unknown>,
  ) => {
    const temporary = mandateOverride.trim()
    void chat.sendMessage(
      message,
      model,
      provider,
      scope,
      viewContext,
      temporary ? { perspective: temporary } : undefined,
    )
    if (temporary) setMandateOverride("")
  }

  const openDocument = async (filename: string, page?: number) => {
    try {
      const result = await evidenceAPI.findByFilename(filename, caseId!)
      if (!result.found || !result.evidence_id) {
        toast.error("Source file not found")
        return
      }

      setViewerDoc({
        evidenceId: result.evidence_id,
        url: evidenceAPI.getFileUrl(result.evidence_id),
        name: filename,
        page,
      })
    } catch {
      toast.error("Failed to load source file")
    }
  }

  return (
    <div className="flex h-full bg-background">
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
          defaultSize={resultGraphPanelOpen ? "55" : "100"}
          minSize="30"
        >
          <div className="flex h-full flex-col min-w-0">
            <ChatHeader caseId={caseId!} />
            <MandateUsageBanner
              versionNumber={chat.mandate?.version?.version_number ?? caseContext.data?.active_mandate?.version_number}
              activeVersionNumber={chat.mandate?.active_version_number ?? caseContext.data?.active_mandate?.version_number}
              stale={chat.mandate?.is_stale}
              incomplete={chat.mandate ? chat.mandate.is_incomplete : !caseContext.data?.active_mandate}
              temporaryOverride={mandateOverride}
              onTemporaryOverrideChange={setMandateOverride}
              onAdoptCurrent={chat.mandate?.is_stale ? chat.adoptCurrentMandate : undefined}
            />

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
                  onDocumentClick={openDocument}
                />
              )}
            </div>

            {/* Input */}
            <ChatInput
              key={`${caseId}:${caseLayer}`}
              onSend={sendWithMandate}
              isLoading={chat.isLoading}
              contextNodes={context.selectedNodes}
              contextDocument={context.scopedDocument}
              suggestions={chat.suggestions}
              caseLayer={caseLayer}
              isReadOnly={isReadOnly}
            />
          </div>
        </ResizablePanel>

        {/* Result graph — resizable right panel */}
        {resultGraphPanelOpen && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel
              id="chat-result-graph"
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

      <DocumentViewer
        caseId={caseId}
        evidenceId={viewerDoc?.evidenceId}
        open={!!viewerDoc}
        onOpenChange={(open) => {
          if (!open) setViewerDoc(null)
        }}
        documentUrl={viewerDoc?.url}
        documentName={viewerDoc?.name}
        initialPage={viewerDoc?.page}
      />
    </div>
  )
}
