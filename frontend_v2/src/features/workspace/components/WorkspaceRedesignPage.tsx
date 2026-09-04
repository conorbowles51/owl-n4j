import { useSearchParams } from "react-router-dom"
import { BriefcaseBusiness, FolderKanban, LayoutDashboard, FileText, Lightbulb, ShieldCheck } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import { CanonicalWorkspaceOverview } from "./CanonicalWorkspaceOverview"
import { CaseworkListView } from "./CaseworkListView"
import { TasksSection } from "./TasksSection"

export function WorkspaceRedesignPage({ caseId }: { caseId: string }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedView = searchParams.get("view")
  const section = requestedView === "casework" || requestedView === "work" ? requestedView : "overview"
  const caseworkSection = searchParams.get("kind") === "theory" ? "theories" : searchParams.get("kind") === "note" ? "notes" : "findings"
  const selectedEntryId = section === "casework" ? searchParams.get("entry") : null
  const selectedWorkItemId = section === "work" ? searchParams.get("item") : null
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)

  const setSection = (view: string) => {
    const next = new URLSearchParams(searchParams)
    if (view === "overview") next.delete("view")
    else next.set("view", view)
    next.delete("item")
    next.delete("entry")
    setSearchParams(next, { replace: true })
  }

  const setCaseworkSection = (value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === "theories") next.set("kind", "theory")
    else if (value === "notes") next.set("kind", "note")
    else next.delete("kind")
    next.delete("entry")
    setSearchParams(next, { replace: true })
  }

  return (
    <Tabs value={section} onValueChange={setSection} className="flex h-full flex-col bg-background">
      <div className="border-b border-border bg-card/95 px-3 backdrop-blur-sm sm:px-4">
        <TabsList variant="line" className="h-11">
          <TabsTrigger value="overview"><LayoutDashboard className="size-3.5" /> Overview</TabsTrigger>
          <TabsTrigger value="casework"><FolderKanban className="size-3.5" /> Casework</TabsTrigger>
          <TabsTrigger value="work"><BriefcaseBusiness className="size-3.5" /> Work</TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="overview" className="min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full"><CanonicalWorkspaceOverview caseId={caseId} canEdit={canEdit} onOpenCasework={() => setSection("casework")} /></ScrollArea>
      </TabsContent>

      <TabsContent value="casework" className="min-h-0 flex-1 overflow-hidden">
        <Tabs value={caseworkSection} onValueChange={setCaseworkSection} className="flex h-full flex-col">
          <div className="border-b border-border bg-muted/15 px-4">
            <TabsList variant="line" className="h-9">
              <TabsTrigger value="notes"><FileText className="size-3.5" /> Notes</TabsTrigger>
              <TabsTrigger value="findings"><ShieldCheck className="size-3.5" /> Findings</TabsTrigger>
              <TabsTrigger value="theories"><Lightbulb className="size-3.5" /> Theories</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="notes" className="min-h-0 flex-1 overflow-hidden"><ScrollArea className="h-full"><div className="mx-auto max-w-6xl p-4 sm:p-5"><CaseworkListView caseId={caseId} entryType="note" canEdit={canEdit} initialSelectedEntryId={selectedEntryId} /></div></ScrollArea></TabsContent>
          <TabsContent value="findings" className="min-h-0 flex-1 overflow-hidden"><ScrollArea className="h-full"><div className="mx-auto max-w-6xl p-4 sm:p-5"><CaseworkListView caseId={caseId} entryType="finding" canEdit={canEdit} initialSelectedEntryId={selectedEntryId} /></div></ScrollArea></TabsContent>
          <TabsContent value="theories" className="min-h-0 flex-1 overflow-hidden"><ScrollArea className="h-full"><div className="mx-auto max-w-6xl p-4 sm:p-5"><CaseworkListView caseId={caseId} entryType="theory" canEdit={canEdit} initialSelectedEntryId={selectedEntryId} /></div></ScrollArea></TabsContent>
        </Tabs>
      </TabsContent>

      <TabsContent value="work" className="min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full"><div className="mx-auto max-w-5xl p-4 sm:p-5"><TasksSection caseId={caseId} canEdit={canEdit} initialItemId={selectedWorkItemId} /></div></ScrollArea>
      </TabsContent>
    </Tabs>
  )
}
