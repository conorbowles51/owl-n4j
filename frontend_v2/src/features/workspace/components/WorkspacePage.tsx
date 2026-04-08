import { useParams } from "react-router-dom"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  LayoutDashboard,
  Lightbulb,
  CheckSquare,
  Users,
  AlertCircle,
  History,
} from "lucide-react"
import { WorkspaceOverview } from "./WorkspaceOverview"
import { TheoriesSection } from "./TheoriesSection"
import { TasksSection } from "./TasksSection"
import { WitnessMatrixSection } from "./WitnessMatrixSection"
import { FindingsSection } from "./FindingsSection"
import { TimelineSection } from "./TimelineSection"

export function WorkspacePage() {
  const { id: caseId } = useParams()

  if (!caseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <Tabs defaultValue="overview" className="flex h-full flex-col">
      <div className="border-b border-border px-4">
        <TabsList variant="line" className="h-10">
          <TabsTrigger value="overview">
            <LayoutDashboard className="size-3.5" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="findings">
            <AlertCircle className="size-3.5" />
            Findings
          </TabsTrigger>
          <TabsTrigger value="theories">
            <Lightbulb className="size-3.5" />
            Theories
          </TabsTrigger>
          <TabsTrigger value="tasks">
            <CheckSquare className="size-3.5" />
            Tasks
          </TabsTrigger>
          <TabsTrigger value="witnesses">
            <Users className="size-3.5" />
            Witnesses
          </TabsTrigger>
          <TabsTrigger value="timeline">
            <History className="size-3.5" />
            Timeline
          </TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="overview" className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <WorkspaceOverview caseId={caseId} />
        </ScrollArea>
      </TabsContent>

      <TabsContent value="findings" className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-4xl p-4">
            <FindingsSection caseId={caseId} />
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="theories" className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-4xl p-4">
            <TheoriesSection caseId={caseId} />
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="tasks" className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-4xl p-4">
            <TasksSection caseId={caseId} />
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="witnesses" className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-4xl p-4">
            <WitnessMatrixSection caseId={caseId} />
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="timeline" className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-4xl p-4">
            <TimelineSection caseId={caseId} />
          </div>
        </ScrollArea>
      </TabsContent>
    </Tabs>
  )
}
