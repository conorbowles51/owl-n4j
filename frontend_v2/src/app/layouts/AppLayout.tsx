import { useEffect } from "react"
import { Outlet, useMatch } from "react-router-dom"
import { AppSidebar } from "@/components/ui/sidebar"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useUIStore } from "@/stores/ui.store"
import { ChatSidePanel } from "@/features/chat/components/ChatSidePanel"

export function AppLayout() {
  const chatPanelOpen = useUIStore((s) => s.chatPanelOpen)
  const setChatPanelOpen = useUIStore((s) => s.setChatPanelOpen)
  const caseMatch = useMatch("/cases/:id/*")
  const currentCaseId = caseMatch?.params.id ?? null
  const isGraphRoute = !!useMatch("/cases/:id/graph")

  const graphPanelCollapsed = useUIStore((s) => s.graphPanelCollapsed)
  const graphPanelTab = useUIStore((s) => s.graphPanelTab)
  const setGraphPanelCollapsed = useUIStore((s) => s.setGraphPanelCollapsed)
  const expandGraphPanelTo = useUIStore((s) => s.expandGraphPanelTo)

  // Keyboard shortcut: Ctrl+Shift+L — works globally
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === "L") {
        e.preventDefault()
        if (isGraphRoute) {
          // On graph route: toggle graph panel to chat
          if (!graphPanelCollapsed && graphPanelTab === "chat") {
            setGraphPanelCollapsed(true)
          } else {
            expandGraphPanelTo("chat")
          }
        } else {
          setChatPanelOpen(!chatPanelOpen)
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [chatPanelOpen, setChatPanelOpen, isGraphRoute, graphPanelCollapsed, graphPanelTab, setGraphPanelCollapsed, expandGraphPanelTo])

  const showAppChat = chatPanelOpen && !isGraphRoute && !!currentCaseId

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <AppSidebar />
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        <ResizablePanel id="main-content" order={1} defaultSize="100" minSize="40">
          <main className="h-full overflow-hidden">
            <ErrorBoundary level="page">
              <Outlet />
            </ErrorBoundary>
          </main>
        </ResizablePanel>
        {showAppChat && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel id="chat-panel" order={2} defaultSize="25" minSize="20" maxSize="45">
              <ChatSidePanel caseId={currentCaseId} />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    </div>
  )
}
