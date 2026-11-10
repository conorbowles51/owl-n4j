import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { Bot, CheckCheck, FilePenLine, House, Settings2 } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import { CanonicalWorkspaceOverview } from "./CanonicalWorkspaceOverview"
import { CaseworkListView } from "./CaseworkListView"
import { TasksSection } from "./TasksSection"
import { AgentProposalsPanel } from "@/features/workspace-ai/components/AgentProposalsPanel"
import { CaseContextSection } from "./CaseContextSection"
import { confirmUnsavedNavigation } from "@/hooks/use-unsaved-history-guard"

export function WorkspaceRedesignPage({ caseId }: { caseId: string }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [setupDirty, setSetupDirty] = useState(false)
  useEffect(() => {
    if (!setupDirty) return
    const warn = (event: MouseEvent) => {
      const link = (event.target as Element)?.closest?.("a[href]")
      if (link && !window.confirm("Discard your unsaved setup changes?")) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    document.addEventListener("click", warn, true)
    return () => document.removeEventListener("click", warn, true)
  }, [setupDirty])
  const requestedView = searchParams.get("view")
  const section =
    requestedView === "casework" ||
    requestedView === "work" ||
    requestedView === "proposals" ||
    requestedView === "setup"
      ? requestedView
      : "overview"
  const kind = searchParams.get("kind")
  const caseworkType =
    kind === "theory" || kind === "note" || kind === "finding" ? kind : "all"
  const selectedEntryId =
    section === "casework" ? searchParams.get("entry") : null
  const selectedWorkItemId =
    section === "work" ? searchParams.get("item") : null
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)

  const setSection = (view: string) => {
    if (!confirmUnsavedNavigation()) return
    const next = new URLSearchParams(searchParams)
    if (view === "overview") next.delete("view")
    else next.set("view", view)
    next.delete("item")
    next.delete("entry")
    next.delete("kind")
    setSearchParams(next)
  }

  const setCaseworkSection = (value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === "all") next.delete("kind")
    else next.set("kind", value)
    next.delete("entry")
    setSearchParams(next)
  }

  return (
    <Tabs
      value={section}
      onValueChange={setSection}
      className="flex h-full flex-col bg-background"
    >
      <div className="shrink-0 overflow-x-auto border-b border-border/70 px-4 sm:px-8">
        <TabsList
          variant="line"
          className="h-12 min-w-max gap-2 sm:gap-5"
          aria-label="Workspace sections"
        >
          <TabsTrigger value="overview" className="min-h-10">
            <House className="size-3.5" /> Overview
          </TabsTrigger>
          <TabsTrigger value="casework" className="min-h-10">
            <FilePenLine className="size-3.5" /> Casework
          </TabsTrigger>
          <TabsTrigger value="work" className="min-h-10">
            <CheckCheck className="size-3.5" /> Tasks & deadlines
          </TabsTrigger>
          <TabsTrigger value="setup" className="min-h-10">
            <Settings2 className="size-3.5" /> Case setup
          </TabsTrigger>
          <TabsTrigger value="proposals" className="min-h-10">
            <Bot className="size-3.5" /> Agent proposals
          </TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="overview" className="min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <CanonicalWorkspaceOverview
            key={caseId}
            caseId={caseId}
            caseName={caseQuery.data?.title}
            canEdit={canEdit}
            onOpenCasework={() => setSection("casework")}
          />
        </ScrollArea>
      </TabsContent>

      <TabsContent value="casework" className="min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-[1200px] px-5 py-8 sm:px-9 lg:px-12">
            <CaseworkListView
              key={caseId}
              caseId={caseId}
              entryType={caseworkType}
              onEntryTypeChange={setCaseworkSection}
              canEdit={canEdit}
              initialSelectedEntryId={selectedEntryId}
            />
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="setup" className="min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-[1200px] px-5 py-8 sm:px-9 lg:px-12">
            <header className="mb-8">
              <h1 className="font-display text-2xl font-semibold tracking-tight">
                Case setup
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
                The context and objective that guide the investigation. Existing
                details stay with the case as your work develops.
              </p>
            </header>
            <CaseContextSection
              key={caseId}
              caseId={caseId}
              canEdit={canEdit}
              onDirtyChange={setSetupDirty}
            />
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="proposals" className="min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-[1200px] px-5 py-8 sm:px-9 lg:px-12">
            <AgentProposalsPanel caseId={caseId} canEdit={canEdit} />
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="work" className="min-h-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-[1200px] px-5 py-8 sm:px-9 lg:px-12">
            <TasksSection
              key={caseId}
              caseId={caseId}
              canEdit={canEdit}
              initialItemId={selectedWorkItemId}
            />
          </div>
        </ScrollArea>
      </TabsContent>
    </Tabs>
  )
}
