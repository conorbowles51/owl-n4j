/**
 * The one way to send evidence files to the document pipeline.
 *
 * Every process button in the application goes through this hook, and
 * `use-guarded-process.test.tsx` fails if a new one does not.  That is not
 * tidiness: the check that decides whether a file is a bank statement runs
 * here, and a button wired straight to `evidenceAPI.processBackground` is a
 * door around it.  There were seven such doors before this hook existed.
 *
 * Why the interface is the gate at all
 * -----------------------------------
 *
 * `POST /api/evidence/process/background` does not consult the route check.
 * The evidence engine has a backstop in `run_pipeline`, but it refuses only
 * files exactly one native format claims -- an ambiguous file passes it -- and
 * it refuses by failing the job after the upload has already happened.  So this
 * is the only place that can turn a bank file away before the work is paid for
 * and offer the person a choice about it.
 *
 * Failing closed
 * --------------
 *
 * If the check cannot be run -- the endpoint is missing because the backend is
 * older than this bundle, the network failed, the service is down -- the
 * request is held rather than allowed through.  This is the same rule
 * `coerceOutcome` applies to an outcome it does not recognise, for the same
 * reason: not knowing what a file is has to mean "stop", or every failure of
 * the check becomes a silent green light, and the failure being guarded against
 * is a bank statement's figures being inferred from prose by a language model
 * and then being indistinguishable from figures that were parsed.
 *
 * A held request is not a refusal.  The caller is handed the list, and the
 * files the check cleared can still be sent on with {@link release}.
 */

import { useCallback, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { evidenceAPI } from "../api"
import { blocksDocumentProcessing, coerceOutcome, type RouteOutcome } from "../utils/financial-route"
import type { FileRouteCheck, RouteCheckSummary } from "@/types/evidence.types"

export interface ProcessRequest {
  fileIds: string[]
  profile?: string
  maxWorkers?: number
  imageProvider?: string
}

/**
 * One file the check will not let past, with its outcome narrowed.
 *
 * `outcome` is a `RouteOutcome` here and a `string` on the wire, because
 * narrowing happens once, at the edge, where an unrecognised value can still be
 * turned into one that blocks.
 */
export interface HeldFile extends Omit<FileRouteCheck, "outcome"> {
  outcome: RouteOutcome
}

export interface HeldRequest {
  /** Exactly what was asked for, so releasing or admitting can reuse it. */
  request: ProcessRequest
  /** The files that must not go unattended. Empty when `checkError` is set. */
  held: HeldFile[]
  /** The file ids the check cleared. Empty when `checkError` is set. */
  cleared: string[]
  summary: RouteCheckSummary | null
  /**
   * Why no answer was obtained, or null when the check ran.
   *
   * Set means nothing is known about any of these files, which is why `held`
   * and `cleared` are both empty rather than the request being split.
   */
  checkError: string | null
}

/**
 * What became of a request.
 *
 * `failed` exists so that {@link useGuardedProcess.start} never rejects.  Seven
 * call sites awaiting a promise that can throw is seven chances to forget a
 * `try`, and a forgotten one is an unhandled rejection plus a button that
 * silently did nothing.  The hook reports the failure itself and says so here.
 */
export type StartOutcome = "started" | "held" | "empty" | "failed"

/**
 * One sentence saying what was held and what was not.
 *
 * Shared so that seven screens cannot describe the same event seven different
 * ways.  {@link ProcessHoldDialog} shows it as the dialog's description rather
 * than its title -- an earlier draft of this comment said "title", but the
 * sentence has two clauses and a heading with two clauses is a paragraph.  The
 * title says how many were held; this says what became of the rest.
 *
 * It always says what happened to the files that were *not* held, because
 * "held" on its own reads as "nothing happened", and the difference between
 * nothing happening and most of it happening is the thing a person needs.
 */
export function describeHold(held: HeldRequest): string {
  // `checkError` alone does not mean nothing is known: it is also set when the
  // check answered for only some of the files, and in that case the rest were
  // still sorted. Only an empty result on both sides means the check itself
  // failed, which is the one case where there is nothing else to report.
  if (held.held.length === 0 && held.cleared.length === 0) {
    return `Nothing was sent: the files could not be checked. ${held.checkError ?? ""}`.trim()
  }

  const bank =
    held.held.length === 1
      ? "1 file looks like bank records and was held back."
      : held.held.length > 1
        ? `${held.held.length} files look like bank records and were held back.`
        : ""
  const unanswered = held.checkError ? ` ${held.checkError}` : ""
  const ready =
    held.cleared.length === 1
      ? " 1 other file is ready to process."
      : held.cleared.length > 1
        ? ` ${held.cleared.length} other files are ready to process.`
        : ""
  return `${bank}${unanswered}${ready}`.trim()
}

const QUERY_KEYS_TO_REFRESH = [
  "evidence-jobs",
  "evidence-folder-contents",
  "evidence-folder-tree",
  "evidence",
] as const

export function useGuardedProcess(caseId: string) {
  const queryClient = useQueryClient()
  const [held, setHeld] = useState<HeldRequest | null>(null)
  const [isChecking, setIsChecking] = useState(false)

  const processMutation = useMutation({
    mutationFn: (request: ProcessRequest) =>
      evidenceAPI.processBackground(
        caseId,
        request.fileIds,
        request.profile,
        request.maxWorkers,
        request.imageProvider
      ),
    onSuccess: async () => {
      // The four keys every previous copy of this mutation invalidated, plus
      // the background-tasks key the detail hook also invalidated. Collected
      // here so that a screen added later cannot forget one of them.
      queryClient.invalidateQueries({ queryKey: ["background-tasks"] })
      for (const key of QUERY_KEYS_TO_REFRESH) {
        queryClient.invalidateQueries({ queryKey: [key, caseId] })
      }
      await queryClient.refetchQueries({ queryKey: ["evidence-jobs", caseId], type: "active" })
    },
  })

  /**
   * Record a hold.  Saying so is {@link ProcessHoldDialog}'s job.
   *
   * This used to raise a toast here, on the reasoning that a screen which
   * forgot to announce a hold would leave a button that visibly does nothing.
   * That reasoning still holds; what changed is who satisfies it.  A toast can
   * only report, and the useful thing about a hold is the choice it comes with
   * -- send the rest, or send nothing -- which needs somewhere to put two
   * buttons.  Keeping both would have every screen state the same sentence
   * twice at once.
   *
   * So the obligation moved rather than lapsed: `no unannounced hold` in
   * `use-guarded-process.test.tsx` fails if any module calling this hook does
   * not also render the dialog.
   */
  const hold = useCallback((request: HeldRequest): StartOutcome => {
    setHeld(request)
    return "held"
  }, [])

  /**
   * Send the request on, reporting a failure rather than throwing one.
   *
   * See {@link StartOutcome} for why this does not simply reject.
   */
  const send = useCallback(
    async (request: ProcessRequest): Promise<StartOutcome> => {
      try {
        await processMutation.mutateAsync(request)
        return "started"
      } catch (error) {
        toast.error(error instanceof Error ? error.message : String(error))
        return "failed"
      }
    },
    [processMutation]
  )

  /**
   * Check these files, then either send them or hold them.
   *
   * Resolves to what happened so the caller can decide what to say. It does not
   * throw on a held request: being held is an ordinary answer, not a fault.
   */
  const start = useCallback(
    async (request: ProcessRequest): Promise<StartOutcome> => {
      if (request.fileIds.length === 0) return "empty"

      setIsChecking(true)
      let response
      try {
        response = await evidenceAPI.routeCheck(caseId, request.fileIds)
      } catch (error) {
        return hold({
          request,
          held: [],
          cleared: [],
          summary: null,
          checkError: error instanceof Error ? error.message : String(error),
        })
      } finally {
        setIsChecking(false)
      }

      const heldFiles: HeldFile[] = []
      const cleared: string[] = []
      for (const file of response.files) {
        const outcome = coerceOutcome(file.outcome)
        // The server's own verdict is not trusted over the local rule. An
        // older service computed `blocks_document_processing` without knowing
        // about outcomes added since, and the two disagreeing must resolve
        // towards holding rather than towards processing.
        if (blocksDocumentProcessing(outcome) || file.blocks_document_processing) {
          heldFiles.push({ ...file, outcome })
        } else {
          cleared.push(file.file_id)
        }
      }

      // A file id the check did not answer for is not a file this build can say
      // anything about, so it is not quietly added to the cleared list.
      const answered = new Set(response.files.map((file) => file.file_id))
      const unanswered = request.fileIds.filter((id) => !answered.has(id))

      if (heldFiles.length === 0 && unanswered.length === 0) {
        return send(request)
      }

      return hold({
        request,
        held: heldFiles,
        cleared,
        summary: response.summary,
        checkError:
          unanswered.length > 0
            ? `The check returned no answer for ${unanswered.length} of ${request.fileIds.length} files.`
            : null,
      })
    },
    [caseId, hold, send]
  )

  /**
   * Send on only the files the check cleared, leaving the rest alone.
   *
   * Resolves to the number actually sent.  That is zero when the check itself
   * failed -- nothing was cleared, because nothing was learned -- and also zero
   * when the send failed, since in both cases no file went anywhere.  Like
   * {@link start} this reports rather than throws.
   */
  const release = useCallback(async (): Promise<number> => {
    if (!held || held.cleared.length === 0) {
      setHeld(null)
      return 0
    }
    const count = held.cleared.length
    const outcome = await send({ ...held.request, fileIds: held.cleared })
    setHeld(null)
    return outcome === "started" ? count : 0
  }, [held, send])

  const dismiss = useCallback(() => setHeld(null), [])

  return {
    // Returned rather than left in the closure because the hold dialog has to
    // offer a native bank file somewhere to go, and both ends of that road
    // need the case.  Putting it on the gate means every screen that already
    // renders the dialog gets it with no change of its own; a new prop on the
    // dialog would be seven call sites and seven chances to forget one, which
    // is the argument {@link ProcessGate} already makes about `held`,
    // `release` and `dismiss`.
    caseId,
    start,
    release,
    dismiss,
    held,
    isChecking,
    isProcessing: processMutation.isPending,
  }
}

/**
 * Everything one call to the gate returns.
 *
 * Exported so that {@link ProcessHoldDialog} can take the whole thing as a
 * single prop.  Passing `held`, `release` and `dismiss` separately would be
 * three chances for a screen to wire two of them and think it was done; one
 * prop is either present or it is not, and the scanner test can see which.
 */
export type ProcessGate = ReturnType<typeof useGuardedProcess>
