/**
 * What the gate held, and the only choice it can currently offer about it.
 *
 * `useGuardedProcess` refuses to send certain files to the document pipeline
 * and records why.  Nothing consumed that record until this component existed,
 * so a held request was a toast and then nothing -- the person was told a file
 * had been held and given no way to act on it except to try again and be
 * refused again.
 *
 * The choice on offer is deliberately narrow: send the files that were
 * cleared, or send nothing.  There is no "process it anyway" here yet, because
 * admitting a bank file to prose processing is a decision somebody has to own,
 * and there is nowhere in the schema to record who owned it -- `decisions.record`
 * files adjudications against financial subjects, and an evidence file admitted
 * to the document pipeline never becomes one.  A button that discarded the
 * reason would be worse than no button: it would look like an audit trail.
 *
 * Not a safety control
 * --------------------
 *
 * The gate decides.  This explains.  If this component were missing from a
 * screen the file would still be held -- the failure would be a button that
 * appears to do nothing, which is why `no unannounced hold` in
 * `use-guarded-process.test.tsx` names any module that calls the hook without
 * rendering this.
 *
 * Why it does not reuse RouteBadge
 * --------------------------------
 *
 * `RouteBadge` renders nothing for `not_native`, because an ordinary document
 * needs no label on a list of a thousand files.  But a `not_native` file can be
 * held: the service sets `blocks_document_processing` for reasons its outcome
 * word does not carry, and the gate honours that flag.  Such a file appears in
 * this list, and reusing the badge would print its name with no label beside
 * it -- the one row here that explained nothing.
 */

import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  ROUTE_OUTCOME_LABEL,
  ROUTE_OUTCOME_VARIANT,
  routeDetailLines,
} from "../utils/financial-route"
import { describeHold } from "../hooks/use-guarded-process"
import type { HeldRequest, ProcessGate } from "../hooks/use-guarded-process"

interface ProcessHoldDialogProps {
  /**
   * The whole gate, not its pieces.
   *
   * See {@link ProcessGate}: three separate props would be three chances to
   * wire two of them.
   */
  gate: ProcessGate
}

/**
 * The heading, which says how many rather than what became of the rest.
 *
 * Four shapes, because a hold has four: nothing could be checked, some files
 * could not be checked but the rest were sorted, files were held, or both.
 * `held.length` alone gets the second of those wrong -- it would read
 * "0 files were held back" over a dialog that exists precisely because
 * something went unanswered.
 *
 * Deliberately not exported.  Its four shapes are asserted through the rendered
 * heading rather than by calling it, which is both closer to what a person sees
 * and the reason this file can stay a file that exports only a component --
 * `react-refresh/only-export-components`, which is a real constraint here and
 * not a style rule.
 */
function holdTitle(held: HeldRequest): string {
  if (held.held.length === 0 && held.cleared.length === 0) return "Nothing was sent"
  if (held.held.length === 0) return "Some files could not be checked"
  return held.held.length === 1 ? "1 file was held back" : `${held.held.length} files were held back`
}

export function ProcessHoldDialog({ gate }: ProcessHoldDialogProps) {
  // Declared before the early return, so that a hold arriving does not change
  // how many hooks this component runs.
  const [isReleasing, setIsReleasing] = useState(false)
  const held = gate.held

  if (!held) return null

  const heldFiles = held.held
  const clearedCount = held.cleared.length

  const handleRelease = async () => {
    setIsReleasing(true)
    // `release` reports rather than throws, and announces its own failure --
    // see `send` in the gate. So a zero here has already been explained, and
    // saying anything more would be a second message about one event.
    const sent = await gate.release()
    // Reset after awaiting rather than on unmount: the dialog closes by `held`
    // becoming null, which renders nothing but keeps this state alive. Left
    // true, the next hold would open showing a spinner over a button nobody
    // had pressed.
    setIsReleasing(false)
    if (sent > 0) toast.success(`Processing ${sent} file${sent === 1 ? "" : "s"}`)
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        // Escape and the overlay dismiss, they do not release. Losing a
        // modal by accident must not send anything anywhere.
        if (!open && !isReleasing) gate.dismiss()
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-amber-500" />
            {holdTitle(held)}
          </DialogTitle>
          <DialogDescription>{describeHold(held)}</DialogDescription>
        </DialogHeader>

        {heldFiles.length > 0 && (
          <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
            {heldFiles.map((file) => (
              <div
                key={file.file_id}
                className="rounded-md border border-border/70 bg-muted/30 p-3"
              >
                <div className="flex items-start gap-2">
                  <Badge
                    variant={ROUTE_OUTCOME_VARIANT[file.outcome]}
                    className="shrink-0 text-[10px]"
                  >
                    {ROUTE_OUTCOME_LABEL[file.outcome]}
                  </Badge>
                  {/* The id is the fallback because a file with no name still
                      has to be findable on the list behind this dialog. */}
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">
                    {file.file_name ?? file.file_id}
                  </span>
                </div>
                {routeDetailLines(file).map((line) => (
                  <p key={line} className="mt-1.5 text-xs text-muted-foreground">
                    {line}
                  </p>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* Shown on its own only when there is no file list to attach it to.
            Alongside a list it would repeat the description above it. */}
        {held.checkError && heldFiles.length === 0 && (
          <p className="rounded-md border border-border/70 bg-muted/30 p-3 text-xs text-muted-foreground">
            {held.checkError}
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={gate.dismiss} disabled={isReleasing}>
            {clearedCount > 0 ? "Cancel" : "Close"}
          </Button>
          {clearedCount > 0 && (
            <Button onClick={handleRelease} disabled={isReleasing}>
              {isReleasing && <LoadingSpinner className="mr-1.5 size-3.5" />}
              Process {clearedCount} other file{clearedCount === 1 ? "" : "s"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
