import { useState } from "react"
import {
  MessageSquare,
  Plus,
  Search,
  Trash2,
  Pencil,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"
import { useChatStore } from "../stores/chat.store"
import {
  useConversations,
  useDeleteConversation,
  useUpdateConversation,
} from "../hooks/use-conversations"
import type { ConversationSummary } from "../types"

interface ConversationSidebarProps {
  caseId: string
  onNewChat: () => void
  onSelectConversation: (id: string) => void
}

export function ConversationSidebar({
  caseId,
  onNewChat,
  onSelectConversation,
}: ConversationSidebarProps) {
  const [search, setSearch] = useState("")
  const [renameDialog, setRenameDialog] = useState<ConversationSummary | null>(
    null
  )
  const [renameValue, setRenameValue] = useState("")
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  const isOpen = useChatStore((s) => s.conversationPanelOpen)
  const setOpen = useChatStore((s) => s.setConversationPanelOpen)
  const activeId = useChatStore((s) => s.activeConversationId)

  const { data: conversations = [] } = useConversations(caseId)
  const deleteMutation = useDeleteConversation()
  const updateMutation = useUpdateConversation()

  const filteredConversations = conversations.filter(
    (c) => !search || c.name.toLowerCase().includes(search.toLowerCase())
  )

  const handleRename = async () => {
    if (!renameDialog || !renameValue.trim()) return
    try {
      await updateMutation.mutateAsync({
        chatId: renameDialog.id,
        data: { name: renameValue.trim() },
      })
      setRenameDialog(null)
    } catch {
      // Silent fail
    }
  }

  const handleDelete = () => {
    if (!deleteConfirm) return
    deleteMutation.mutate(deleteConfirm)
    if (activeId === deleteConfirm) {
      onNewChat()
    }
    setDeleteConfirm(null)
  }

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return "just now"
    if (diffMin < 60) return `${diffMin}m ago`
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return `${diffH}h ago`
    const diffD = Math.floor(diffH / 24)
    if (diffD === 1) return "yesterday"
    return date.toLocaleDateString()
  }

  // Collapsed state — just toggle button
  if (!isOpen) {
    return (
      <div className="flex flex-col items-center border-r border-border py-2 px-1 gap-2">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setOpen(true)}
          title="Open conversations"
        >
          <PanelLeftOpen className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onNewChat}
          title="New chat"
        >
          <Plus className="size-4 text-amber-500" />
        </Button>
      </div>
    )
  }

  return (
    <div className="flex w-60 flex-col border-r border-border">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-1">
        <span className="text-xs font-semibold text-muted-foreground">
          Conversations
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setOpen(false)}
        >
          <PanelLeftClose className="size-3.5" />
        </Button>
      </div>

      {/* New chat button */}
      <div className="p-2">
        <Button
          variant="primary"
          size="sm"
          className="w-full"
          onClick={onNewChat}
        >
          <Plus className="size-3.5" />
          New Chat
        </Button>
      </div>

      {/* Search */}
      <div className="px-2 pb-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 size-3 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search..."
            className="h-7 pl-7 text-xs"
          />
        </div>
      </div>

      {/* Conversation list */}
      <ScrollArea className="flex-1">
        {filteredConversations.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <MessageSquare className="mx-auto size-6 text-muted-foreground/40" />
            <p className="mt-2 text-xs text-muted-foreground">
              {search ? "No matching conversations" : "No conversations yet"}
            </p>
          </div>
        ) : (
          <div className="p-1">
            {filteredConversations.map((conv) => (
              <ContextMenu key={conv.id}>
                <ContextMenuTrigger asChild>
                  <button
                    onClick={() => onSelectConversation(conv.id)}
                    className={cn(
                      "flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left transition-colors",
                      activeId === conv.id
                        ? "bg-amber-500/10 text-foreground"
                        : "hover:bg-muted text-foreground/80"
                    )}
                  >
                    <MessageSquare
                      className={cn(
                        "mt-0.5 size-3.5 shrink-0",
                        activeId === conv.id
                          ? "text-amber-500"
                          : "text-muted-foreground"
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">
                        {conv.name}
                      </p>
                      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                        <span>{conv.message_count} msgs</span>
                        <span>&middot;</span>
                        <span>{formatTime(conv.last_message_at)}</span>
                      </div>
                    </div>
                  </button>
                </ContextMenuTrigger>
                <ContextMenuContent>
                  <ContextMenuItem
                    onClick={() => {
                      setRenameValue(conv.name)
                      setRenameDialog(conv)
                    }}
                  >
                    <Pencil className="mr-2 size-3.5" />
                    Rename
                  </ContextMenuItem>
                  <ContextMenuItem
                    onClick={() => setDeleteConfirm(conv.id)}
                    className="text-destructive"
                  >
                    <Trash2 className="mr-2 size-3.5" />
                    Delete
                  </ContextMenuItem>
                </ContextMenuContent>
              </ContextMenu>
            ))}
          </div>
        )}
      </ScrollArea>

      {/* Rename dialog */}
      <Dialog
        open={!!renameDialog}
        onOpenChange={(open) => !open && setRenameDialog(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename conversation</DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRename()}
            autoFocus
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRenameDialog(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleRename}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog
        open={!!deleteConfirm}
        onOpenChange={(open) => !open && setDeleteConfirm(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This action cannot be undone. The conversation and all its messages
            will be permanently deleted.
          </p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteConfirm(null)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
