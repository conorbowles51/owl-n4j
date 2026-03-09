import { BackgroundTasksList } from "./BackgroundTasksList"
import { ProcessingLogViewer } from "./ProcessingLogViewer"

interface ActivityTabProps {
  caseId: string
}

export function ActivityTab({ caseId }: ActivityTabProps) {
  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Tasks section */}
      <div className="flex-1 min-h-0 overflow-auto">
        <h2 className="mb-3 text-sm font-semibold text-foreground">Background Tasks</h2>
        <BackgroundTasksList caseId={caseId} />
      </div>

      {/* Logs section */}
      <div className="shrink-0">
        <h2 className="mb-2 text-sm font-semibold text-foreground">Processing Logs</h2>
        <div className="rounded-lg border border-border bg-[#0d1117] p-0 overflow-hidden">
          <ProcessingLogViewer caseId={caseId} limit={100} polling />
        </div>
      </div>
    </div>
  )
}
