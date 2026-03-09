import { useState } from "react"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { CaseListSidebar } from "./CaseListSidebar"
import { CaseDetailPanel } from "./CaseDetailPanel"
import { DeleteCaseDialog } from "./DeleteCaseDialog"
import type { Case } from "@/types/case.types"

export function CaseManagementPage() {
  const [deleteTarget, setDeleteTarget] = useState<Case | null>(null)

  return (
    <div className="h-full">
      <ResizablePanelGroup orientation="horizontal">
        <ResizablePanel id="case-list" order={1} defaultSize="30" minSize="20" maxSize="50">
          <CaseListSidebar onDeleteCase={setDeleteTarget} />
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel id="case-detail" order={2} defaultSize="70" minSize="40">
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
