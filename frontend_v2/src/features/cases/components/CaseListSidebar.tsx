import { useMemo, useState } from "react"
import { Plus, Search, FolderOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { useCases } from "../hooks/use-cases"
import { useCaseManagementStore } from "../case-management.store"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { CaseListItem } from "./CaseListItem"
import { CreateCaseDialog } from "./CreateCaseDialog"
import type { Case } from "@/types/case.types"

interface CaseListSidebarProps {
  onDeleteCase: (c: Case) => void
}

export function CaseListSidebar({ onDeleteCase }: CaseListSidebarProps) {
  const [search, setSearch] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const { selectedCaseId, setSelectedCaseId, viewMode, setViewMode, sortBy, setSortBy } =
    useCaseManagementStore()
  const user = useAuthStore((s) => s.user)
  const isSuperAdmin =
    user?.role === "super_admin" || user?.global_role === "super_admin"

  const { data: cases, isLoading } = useCases(
    isSuperAdmin ? viewMode : undefined
  )

  const filtered = useMemo(() => {
    let list = cases?.filter(
      (c) =>
        c.title.toLowerCase().includes(search.toLowerCase()) ||
        c.description?.toLowerCase().includes(search.toLowerCase())
    )
    if (list && sortBy === "next_deadline") {
      list = [...list].sort((a, b) => {
        if (!a.next_deadline_date && !b.next_deadline_date) return 0
        if (!a.next_deadline_date) return 1
        if (!b.next_deadline_date) return -1
        return a.next_deadline_date.localeCompare(b.next_deadline_date)
      })
    }
    return list
  }, [cases, search, sortBy])

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <FolderOpen className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">Cases</span>
        <div className="flex-1" />
        <Button
          variant="primary"
          size="sm"
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="size-3.5" />
          New
        </Button>
      </div>

      {/* View mode toggle (super admin only) */}
      {isSuperAdmin && (
        <div className="flex border-b border-border">
          <button
            onClick={() => setViewMode("my_cases")}
            className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
              viewMode === "my_cases"
                ? "border-b-2 border-amber-500 text-amber-500"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            My Cases
          </button>
          <button
            onClick={() => setViewMode("all_cases")}
            className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
              viewMode === "all_cases"
                ? "border-b-2 border-amber-500 text-amber-500"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            All Cases
          </button>
        </div>
      )}

      {/* Search + Sort */}
      <div className="space-y-2 border-b border-border px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search cases..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-7 text-xs"
          />
        </div>
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as "updated_at" | "next_deadline")}>
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="updated_at">Last Updated</SelectItem>
            <SelectItem value="next_deadline">Next Deadline</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Case list */}
      <div className="flex-1 overflow-auto px-2 py-1">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : !filtered?.length ? (
          <EmptyState
            icon={FolderOpen}
            title="No cases"
            description={
              search ? "No matches found" : "Create a case to get started"
            }
            className="py-8"
          />
        ) : (
          <div className="space-y-0.5">
            {filtered.map((c) => (
              <CaseListItem
                key={c.id}
                caseData={c}
                isSelected={selectedCaseId === c.id}
                onSelect={() => setSelectedCaseId(c.id)}
                onDelete={
                  c.is_owner || isSuperAdmin
                    ? () => onDeleteCase(c)
                    : undefined
                }
              />
            ))}
          </div>
        )}
      </div>

      <CreateCaseDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
