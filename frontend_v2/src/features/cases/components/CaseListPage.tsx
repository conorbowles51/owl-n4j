import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Plus, Search, LayoutGrid, List } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PageHeader } from "@/components/ui/page-header"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { CaseCard } from "@/components/ui/case-card"
import { useCases } from "../hooks/use-cases"
import { CreateCaseDialog } from "./CreateCaseDialog"

export function CaseListPage() {
  const { data: cases, isLoading } = useCases()
  const [search, setSearch] = useState("")
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid")
  const [createOpen, setCreateOpen] = useState(false)
  const navigate = useNavigate()

  const filtered = cases?.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.description?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-6 py-3">
        <PageHeader
          title="Cases"
          actions={
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              New Case
            </Button>
          }
        />
      </div>

      <div className="flex items-center gap-3 border-b border-border px-6 py-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search cases..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex gap-1">
          <Button
            variant={viewMode === "grid" ? "outline" : "ghost"}
            size="icon"
            onClick={() => setViewMode("grid")}
          >
            <LayoutGrid className="size-4" />
          </Button>
          <Button
            variant={viewMode === "list" ? "outline" : "ghost"}
            size="icon"
            onClick={() => setViewMode("list")}
          >
            <List className="size-4" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : !filtered?.length ? (
          <EmptyState
            title="No cases found"
            description={
              search
                ? "Try a different search term"
                : "Create your first investigation case to get started"
            }
            action={
              !search && (
                <Button
                  variant="primary"
                  onClick={() => setCreateOpen(true)}
                >
                  <Plus className="size-4" />
                  Create Case
                </Button>
              )
            }
          />
        ) : (
          <div
            className={
              viewMode === "grid"
                ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
                : "flex flex-col gap-3"
            }
          >
            {filtered.map((c) => (
              <CaseCard
                key={c.id}
                name={c.name}
                description={c.description}
                status={c.status}
                memberCount={c.member_count}
                lastUpdated={c.updated_at}
                onClick={() => navigate(`/cases/${c.id}/graph`)}
              />
            ))}
          </div>
        )}
      </div>

      <CreateCaseDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
