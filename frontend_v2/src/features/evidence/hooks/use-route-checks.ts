/**
 * What the route check says about a screenful of files, for labelling them.
 *
 * This is the reading half of the same check {@link useGuardedProcess} runs
 * before processing.  The gate asks about the files a person is about to send;
 * this asks about the files a person is currently looking at, so that a bank
 * statement can be recognised on the list rather than at the moment it is
 * refused.
 *
 * It is not a safety control.  Nothing here decides what may be processed --
 * the gate does that, on its own evidence, at the time of the request.  A
 * failure here costs a label, not a guarantee, which is why this hook is
 * allowed to give up quietly where the gate must hold.
 *
 * Why a batch and not a field
 * ---------------------------
 *
 * `EvidenceFile` carries no column for any of this.  The answer is computed by
 * reading the first few kilobytes of a file, and nothing writes the result
 * back, so the only way to label a list is to ask about the list.  One request
 * per row would be a request per row; this asks once per screen.
 *
 * Why it chunks
 * -------------
 *
 * `/api/evidence/route-check` refuses more than {@link ROUTE_CHECK_BATCH_LIMIT}
 * ids, and a page of this list holds 250.  Without chunking the badge would
 * simply never appear on a full page -- the request would fail with "Too many
 * files" and the column would be silently empty, which looks exactly like a
 * page with nothing interesting on it.
 */

import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import { evidenceAPI } from "../api"
import { coerceOutcome, type RouteOutcome } from "../utils/financial-route"
import type { FileRouteCheck } from "@/types/evidence.types"

/**
 * The most ids one request may carry.
 *
 * Mirrors `MAX_BATCH_SIZE` in `backend/routers/evidence.py`.  Lowering the
 * server's value without lowering this one turns every full page into a failed
 * check, so the two are pinned together in `use-route-checks.test.tsx`.
 */
export const ROUTE_CHECK_BATCH_LIMIT = 50

/**
 * How long an answer is trusted before it is asked for again.
 *
 * An evidence file's bytes do not change once uploaded, so the honest answer is
 * "indefinitely".  It is a finite number anyway because the answer also depends
 * on the detector, and a detector fixed on the server should reach a screen
 * that is already open without needing a reload.
 */
const ROUTE_CHECK_STALE_MS = 5 * 60 * 1000

/** One file's route, with its outcome narrowed to something this build knows. */
export interface FileRoute extends Omit<FileRouteCheck, "outcome"> {
  outcome: RouteOutcome
}

/**
 * The answer before there is one.
 *
 * Shared rather than allocated per render, so that a component reading it does
 * not see a new object every time.  `ReadonlyMap` is what keeps a caller from
 * writing into the shared instance; it is a type, not a runtime guard, which is
 * enough here because nothing outside this module has a reason to write to it.
 */
const NO_ROUTES: ReadonlyMap<string, FileRoute> = new Map()

function chunk<T>(items: readonly T[], size: number): T[][] {
  const chunks: T[][] = []
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size))
  }
  return chunks
}

/**
 * Ask about every id, in as many requests as the batch limit requires.
 *
 * All or nothing on purpose.  A partial result would put a badge on some rows
 * and not others, and because an ordinary document is deliberately unlabelled,
 * a bank file in the chunk that failed would be indistinguishable from one that
 * was checked and found ordinary.  Losing every label says "this is not working
 * right now"; losing some of them says something false about specific files.
 */
async function checkAll(caseId: string, ids: string[]): Promise<Map<string, FileRoute>> {
  const responses = await Promise.all(
    chunk(ids, ROUTE_CHECK_BATCH_LIMIT).map((batch) => evidenceAPI.routeCheck(caseId, batch))
  )

  const routes = new Map<string, FileRoute>()
  for (const response of responses) {
    for (const file of response.files) {
      // Narrowed once, here, for the same reason the gate narrows here: a
      // service newer than this bundle can name an outcome that did not exist
      // when it was built, and a `Record` lookup on that returns `undefined`,
      // which React renders as an empty badge. An empty badge is worse than no
      // badge, because it looks like an answer.
      routes.set(file.file_id, { ...file, outcome: coerceOutcome(file.outcome) })
    }
  }
  return routes
}

/**
 * The route of each of these files, keyed by id.
 *
 * Ids are sorted and de-duplicated before they reach the query key, so that
 * re-ordering a list or rendering the same file twice does not re-ask.
 */
export function useRouteChecks(caseId: string | undefined, fileIds: readonly string[]) {
  const ids = useMemo(() => [...new Set(fileIds)].sort(), [fileIds])

  const query = useQuery({
    queryKey: ["evidence-route-check", caseId, ids],
    queryFn: () => checkAll(caseId!, ids),
    enabled: !!caseId && ids.length > 0,
    staleTime: ROUTE_CHECK_STALE_MS,
  })

  return {
    routes: query.data ?? NO_ROUTES,
    isLoading: query.isLoading,
    error: query.error,
  }
}
