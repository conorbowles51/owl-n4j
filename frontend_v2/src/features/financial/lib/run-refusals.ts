// The app shell reads these (LoadProgress), so this file imports nothing: the run hooks in whole-case-run.ts bring zod.

/**
 * A workbench's answer above its size limit: the server's stated refusal, which a stored whole-case run replaces.
 * Other refusals (a date tolerance, a missing date) stay on the page as they are.
 */
export function isSizeRefusal(message: string | undefined) {
  return /^More than ?[0-9][0-9,]*.*(match|share|comparisons|extensions)|^A threshold candidate contains more than/i.test(
    message ?? ""
  )
}

/** The PDF refusals that numbered parts replace. */
export function isPdfSizeRefusal(message: string | undefined) {
  return /PDF reports support up to|PDF report exceeds|complete ledger record exceeds|Export timed out/i.test(message ?? "")
}

/** A trace or account comparison above one answer's size. */
export function isTraceSizeRefusal(message: string | undefined) {
  return /Tracing requires between 1 and 1000|Cross-account tracing needs 1|complete ledger record exceeds/i.test(message ?? "") || isSizeRefusal(message)
}

/** A refusal the page answers with a stored run: the size of one answer, not a failed read. */
export function opensWholeCaseRun(message: string | null) {
  return !!message && (isSizeRefusal(message) || isPdfSizeRefusal(message) || isTraceSizeRefusal(message))
}
