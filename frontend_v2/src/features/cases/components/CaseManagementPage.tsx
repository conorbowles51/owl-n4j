import { useState } from "react"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useMediaQuery } from "@/hooks/use-media-query"
import { CaseListSidebar } from "./CaseListSidebar"
import { CaseDetailPanel } from "./CaseDetailPanel"
import { DeleteCaseDialog } from "./DeleteCaseDialog"
import type { Case } from "@/types/case.types"

export function CaseManagementPage() {
  const [deleteTarget, setDeleteTarget] = useState<Case | null>(null)
  const stacked = useMediaQuery("(max-width: 639px)")

  return (
    <div className="h-full">
      <ResizablePanelGroup orientation={stacked ? "vertical" : "horizontal"}>
        <ResizablePanel
          id="case-list"
          order={1}
          defaultSize={stacked ? "38" : "30"}
          minSize="20"
          maxSize="50"
          className="bg-panel"
        >
          <CaseListSidebar onDeleteCase={setDeleteTarget} />
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel
          id="case-detail"
          order={2}
          defaultSize={stacked ? "62" : "70"}
          minSize="40"
          className="bg-background"
        >
          <CaseDetailPanel />
        </ResizablePanel>
      </ResizablePanelGroup>

      <DeleteCaseDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        caseToDelete={deleteTarget}
      />
    </div>
  )
}
