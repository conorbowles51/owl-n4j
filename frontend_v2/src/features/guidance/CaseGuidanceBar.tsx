import { useMatch } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { setGuidanceQueryClient } from "./query-client"
import { ChevronDown, History } from "lucide-react"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { GuideMenu } from "./GuideMenu"
import { NextStepsHost } from "./NextStepsHost"
import { StartHere } from "./StartHere"
import { TourHost } from "./TourHost"
import { useGuidance } from "./settings"
import { useEvidenceJobWatcher } from "./watchers"
import { HistoryStrip } from "./history/HistoryStrip"
import { HistoryDocument } from "./history/HistoryDocument"
import { useReturnCheck, useStepRecorder } from "./history/recorder"

/**
 * Guidance and step history inside a case (lx-guide), mounted once by the case layout: the slender bar at the bottom
 * (the last steps, All steps, Guide), the next-step cards above it, the first-visit tour, and Start here on the
 * case home. Every screen gets it without any change of its own.
 */
export default function CaseGuidanceBar({ caseId }: { caseId: string }) {
  setGuidanceQueryClient(useQueryClient())
  useStepRecorder(caseId)
  useReturnCheck(caseId)
  useEvidenceJobWatcher(caseId)
  const home = !!useMatch("/cases/:id/workspace")
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 top-0 z-30">
        <ErrorBoundary fallback={<></>}>
          <NextStepsHost caseId={caseId} />
          {home && <StartHere caseId={caseId} />}
        </ErrorBoundary>
      </div>
      <ErrorBoundary fallback={<></>}>
        <TourHost caseId={caseId} />
        <HistoryDocument caseId={caseId} />
      </ErrorBoundary>
    </>
  )
}

/** The 28 px bar itself; collapsed per person to one History button (saved with the guidance settings). */
export function CaseBottomBar({ caseId }: { caseId: string }) {
  const g = useGuidance(caseId)
  const collapsed = !!g.settings?.history_collapsed
  return (
    <div
      role="region"
      aria-label="Your steps and guidance"
      className={
        collapsed
          ? "relative flex h-7 shrink-0 items-center justify-end gap-1 border-t border-border bg-card px-2"
          : "relative flex h-7 shrink-0 items-center gap-2 border-t border-border bg-card px-2"
      }
    >
      {collapsed ? (
        <button
          type="button"
          data-guide="history-strip"
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] hover:bg-muted"
          disabled={g.saving}
          onClick={() => void g.setHistoryCollapsed(false)}
        >
          <History className="size-3.5" aria-hidden="true" />
          History
        </button>
      ) : (
        <>
          <ErrorBoundary fallback={<span className="flex-1 text-[11px]">Your steps could not be shown.</span>}>
            <HistoryStrip caseId={caseId} />
          </ErrorBoundary>
          <button
            type="button"
            aria-label="Fold the history to one button"
            title="Fold the history to one button"
            className="shrink-0 rounded p-0.5 hover:bg-muted"
            disabled={g.saving}
            onClick={() => void g.setHistoryCollapsed(true)}
          >
            <ChevronDown className="size-3.5" aria-hidden="true" />
          </button>
        </>
      )}
      <GuideMenu caseId={caseId} />
    </div>
  )
}
