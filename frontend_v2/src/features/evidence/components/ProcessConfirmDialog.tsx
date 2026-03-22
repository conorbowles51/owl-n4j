import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Play, FileText, Info } from "lucide-react"
import { useEffectiveProfile } from "../hooks/use-folder-context"
import { ProfileChainPreview } from "./ProfileChainPreview"

/* ------------------------------------------------------------------ */
/*  Props                                                             */
/* ------------------------------------------------------------------ */

interface ProcessConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileCount: number
  folderId?: string | null
  caseId: string
  onConfirm: () => void
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function ProcessConfirmDialog({
  open,
  onOpenChange,
  fileCount,
  folderId,
  caseId,
  onConfirm,
}: ProcessConfirmDialogProps) {
  const { data: effective, isLoading: effectiveLoading } =
    useEffectiveProfile(open && folderId ? folderId : null, caseId)

  const hasProfile =
    effective &&
    (effective.merged_context || Object.keys(effective.merged_overrides ?? {}).length > 0)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80vh] max-w-lg flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Play className="size-4 text-amber-500" />
            Confirm Processing
          </DialogTitle>
          <DialogDescription>
            Review the settings before starting evidence processing.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 -mx-6 px-6">
          <div className="space-y-4 py-1">
            {/* ---- File count banner ---- */}
            <div className="flex items-center gap-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
              <FileText className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
              <div>
                <p className="text-sm font-medium text-foreground">
                  {fileCount} file{fileCount !== 1 ? "s" : ""} selected for
                  processing
                </p>
                <p className="text-[10px] text-muted-foreground">
                  Files will be sent to the evidence engine for entity extraction
                  and graph construction.
                </p>
              </div>
            </div>

            {/* ---- Profile chain (only if folderId provided) ---- */}
            {folderId && (
              <div className="space-y-3">
                {effectiveLoading ? (
                  <div className="flex items-center justify-center gap-2 py-4">
                    <LoadingSpinner size="sm" />
                    <span className="text-xs text-muted-foreground">
                      Loading profile chain...
                    </span>
                  </div>
                ) : effective && effective.chain.length > 0 ? (
                  <ProfileChainPreview chain={effective.chain} />
                ) : (
                  <div className="flex items-start gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
                    <Info className="mt-0.5 size-3.5 shrink-0 text-slate-400" />
                    <p className="text-xs text-muted-foreground">
                      No folder profile configured. Files will be processed with
                      default settings.
                    </p>
                  </div>
                )}

                {/* ---- Merged context ---- */}
                {!effectiveLoading && hasProfile && effective.merged_context && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground">
                      Effective Context
                    </p>
                    <div className="rounded-md border border-border bg-slate-50 p-3 dark:bg-slate-900/50">
                      <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground">
                        {effective.merged_context}
                      </p>
                    </div>
                  </div>
                )}

                {/* ---- Merged overrides summary ---- */}
                {!effectiveLoading &&
                  effective?.merged_overrides &&
                  Object.keys(effective.merged_overrides).length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {effective.merged_overrides.special_entity_types?.map(
                        (et) => (
                          <Badge
                            key={et.name}
                            variant="amber"
                            className="text-[10px]"
                          >
                            {et.name}
                          </Badge>
                        )
                      )}
                      {effective.merged_overrides.temperature !== undefined && (
                        <Badge variant="slate" className="text-[10px]">
                          temp {effective.merged_overrides.temperature}
                        </Badge>
                      )}
                      {effective.merged_overrides.llm_profile && (
                        <Badge variant="info" className="text-[10px]">
                          {effective.merged_overrides.llm_profile}
                        </Badge>
                      )}
                    </div>
                  )}
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={onConfirm}>
            Process {fileCount} file{fileCount !== 1 ? "s" : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
