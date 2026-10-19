/**
 * What a file is, according to whichever side of the system looked at it.
 *
 * Two services answer this question and they do not share code.  The backend's
 * `/api/evidence/route-check` answers it before processing is paid for, so the
 * interface can offer a choice.  The evidence engine's pre-stage answers it
 * again inside `run_pipeline`, for files that arrived by a route that never
 * asked -- a folder scan, a re-process, an API caller of its own.
 *
 * Neither can produce the other's full vocabulary, and that is deliberate
 * rather than untidy.  The engine's `detector_unavailable` exists precisely for
 * the case where the backend package cannot be imported at all, so it cannot be
 * defined in the backend package.  The backend's `not_found` describes a file
 * id that is not in the case, which is a question the engine never asks.  A
 * shared enum would be a union that neither side could wholly return.
 *
 * So the union lives here, in the one place that consumes both, and
 * `financial-route.test.ts` asserts each side's vocabulary against it.  If
 * either service adds an outcome and this file is not updated, that test fails
 * -- which is the whole reason the union was put here rather than being written
 * twice more.
 */

/** Outcomes only the backend's pre-processing check can return. */
export const BACKEND_ONLY_OUTCOMES = ["not_found", "undetermined"] as const

/** Outcomes only the engine's in-pipeline backstop can return. */
export const ENGINE_ONLY_OUTCOMES = ["detector_unavailable"] as const

/** Outcomes both sides can return. */
export const SHARED_OUTCOMES = [
  "native",
  "ambiguous",
  "not_native",
  "unreadable",
] as const

export const ALL_ROUTE_OUTCOMES = [
  ...SHARED_OUTCOMES,
  ...BACKEND_ONLY_OUTCOMES,
  ...ENGINE_ONLY_OUTCOMES,
] as const

export type RouteOutcome = (typeof ALL_ROUTE_OUTCOMES)[number]

/**
 * Outcomes that must stop a file reaching the document pipeline unattended.
 *
 * Mirrors `BLOCKING_OUTCOMES` in `services/financial/route_check.py`, and
 * `financial-route.test.ts` pins the two together.  The rule is not "we know it
 * is a bank file" but "we do not know that it is safe to read as prose", which
 * is why the three uncertain outcomes are here alongside `native`.
 *
 * `not_found` is absent on purpose: an id that is not in this case is not a
 * file this screen can say anything about, and the process call will 404 over
 * it on its own.
 */
export const BLOCKING_OUTCOMES: readonly RouteOutcome[] = [
  "native",
  "ambiguous",
  "unreadable",
  "undetermined",
  "detector_unavailable",
]

export function blocksDocumentProcessing(outcome: RouteOutcome): boolean {
  return BLOCKING_OUTCOMES.includes(outcome)
}

/**
 * True when the file is a bank file the ledger can read directly.
 *
 * Deliberately narrower than {@link blocksDocumentProcessing}: only `native`
 * has a single format the ledger can parse.  An ambiguous file blocks, but
 * sending it to the ledger would fail there too, because the parser requires
 * exactly one claimant.
 */
export function belongsToLedger(outcome: RouteOutcome): boolean {
  return outcome === "native"
}

/** What an outcome is called on screen. */
export const ROUTE_OUTCOME_LABEL: Record<RouteOutcome, string> = {
  native: "Bank file",
  ambiguous: "Format unclear",
  not_native: "Document",
  unreadable: "Could not read",
  undetermined: "Not classified",
  detector_unavailable: "Not checked",
  not_found: "Not in this case",
}

/**
 * The one-line explanation shown under the label.
 *
 * Written to say what will happen rather than what was measured.  "Two formats
 * claim this file" is a fact about a detector; "no parser can be chosen" is the
 * thing the reader has to make a decision about.
 */
export const ROUTE_OUTCOME_DESCRIPTION: Record<RouteOutcome, string> = {
  native:
    "Read directly by the ledger. Processing it as a document would produce figures inferred from text rather than parsed.",
  ambiguous:
    "More than one bank format claims this file, so no parser can be chosen for it. It needs a person to look.",
  not_native: "Handled by the document pipeline as usual.",
  unreadable:
    "The file could not be opened to check. It may be missing, or stored somewhere this service cannot reach.",
  undetermined:
    "The check ran but returned no answer for this file. Treated as unclassified rather than as an ordinary document.",
  detector_unavailable:
    "The format detector could not be loaded, so nothing was checked. Treated as unclassified.",
  not_found: "No file with this id is in this case.",
}

/** Badge colour per outcome, using the variants `badge.tsx` already defines. */
export const ROUTE_OUTCOME_VARIANT: Record<
  RouteOutcome,
  "amber" | "warning" | "slate" | "danger" | "info"
> = {
  native: "amber",
  ambiguous: "warning",
  not_native: "slate",
  unreadable: "danger",
  undetermined: "warning",
  detector_unavailable: "slate",
  not_found: "slate",
}

/** How a native format's short code is written on screen. */
export const NATIVE_FORMAT_LABEL: Record<string, string> = {
  camt053: "camt.053",
  bai2: "BAI2",
  mt940: "MT940",
  nacha: "NACHA",
}

export function formatLabel(code: string): string {
  return NATIVE_FORMAT_LABEL[code] ?? code
}

/** The fields any renderer needs to explain one file's route. */
export interface RouteDetail {
  outcome: RouteOutcome
  detected_format: string | null
  claimants: string[]
  reason: string | null
}

/**
 * Everything there is to say about one file's route, in the order a reader
 * needs it: what will happen, then what was actually found, then whatever the
 * service chose to add.
 *
 * The evidence is included because "format unclear" is not something a person
 * can act on, and "camt.053 and BAI2 both claim this" is.
 *
 * Written once because it is said twice -- in the badge's tooltip on the file
 * list, and in the dialog that appears when the gate holds a request.  Those
 * are the same fact about the same file, and two copies of it would eventually
 * be two different facts.
 */
export function routeDetailLines(route: RouteDetail): string[] {
  const lines = [ROUTE_OUTCOME_DESCRIPTION[route.outcome]]
  if (route.outcome === "native" && route.detected_format) {
    lines.push(`Format: ${formatLabel(route.detected_format)}`)
  }
  if (route.outcome === "ambiguous" && route.claimants.length > 0) {
    lines.push(`Claimed by: ${route.claimants.map(formatLabel).join(", ")}`)
  }
  if (route.reason) lines.push(route.reason)
  return lines
}

/**
 * Whether an unknown string from either service is an outcome this build knows.
 *
 * Used at the edges rather than trusted: a service deployed ahead of this
 * bundle can send an outcome that did not exist when it was built, and a
 * `Record` lookup on it returns `undefined`, which React renders as nothing at
 * all.  A badge with no text is indistinguishable from a file nobody checked.
 */
export function isKnownOutcome(value: string): value is RouteOutcome {
  return (ALL_ROUTE_OUTCOMES as readonly string[]).includes(value)
}

/**
 * An outcome this build understands, or the safest stand-in for one it does not.
 *
 * Unrecognised outcomes become `undetermined`, which blocks.  The alternative
 * -- falling back to `not_native` -- would turn every future outcome into a
 * green light, and the failure it is guarding against is a bank file being read
 * as prose.
 */
export function coerceOutcome(value: string): RouteOutcome {
  return isKnownOutcome(value) ? value : "undetermined"
}
