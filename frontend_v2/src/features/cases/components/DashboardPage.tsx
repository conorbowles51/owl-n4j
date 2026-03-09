import { useNavigate } from "react-router-dom"
import { FolderOpen, Plus } from "lucide-react"
import { PageHeader } from "@/components/ui/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { CaseCard } from "@/components/ui/case-card"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useCases } from "../hooks/use-cases"

export function DashboardPage() {
  const { data: cases, isLoading } = useCases()
  const navigate = useNavigate()

  const recentCases = cases
    ?.sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    )
    .slice(0, 6)

  return (
    <div className="p-6">
      <PageHeader
        title="Dashboard"
        actions={
          <Button variant="primary" onClick={() => navigate("/cases")}>
            <FolderOpen className="size-4" />
            All Cases
          </Button>
        }
      />

      <div className="mt-6">
        <Card>
          <CardHeader>
            <CardTitle>Recent Cases</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex justify-center py-8">
                <LoadingSpinner />
              </div>
            ) : !recentCases?.length ? (
              <EmptyState
                title="No cases yet"
                description="Create your first case to begin investigating"
                action={
                  <Button variant="primary" onClick={() => navigate("/cases")}>
                    <Plus className="size-4" />
                    Create Case
                  </Button>
                }
              />
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {recentCases.map((c) => (
                  <CaseCard
                    key={c.id}
                    title={c.title}
                    description={c.description}
                    userRole={c.user_role}
                    ownerName={c.owner_name}
                    lastUpdated={c.updated_at}
                    onClick={() => navigate(`/cases/${c.id}/graph`)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
