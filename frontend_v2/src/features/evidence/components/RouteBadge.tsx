/**
 * What a file is, said on the row before anyone tries to process it.
 *
 * The point of this badge is a single word on a list of a thousand files: that
 * one is a bank statement, and reading it as prose would produce figures a
 * model inferred rather than figures a parser read.  By the time the gate
 * refuses it, a person has already decided to process it and is now being told
 * no.  This is the same fact, offered earlier and without a decision attached.
 *
 * Silence is the common case
 * --------------------------
 *
 * An ordinary document gets no badge.  Nearly every file is an ordinary
 * document, and a column with a label on all thousand rows is a column nobody
 * reads -- the one badge worth seeing would be hidden by the 999 that were not.
 * So `not_native` renders nothing, and so does a file the check could not
 * answer for.
 *
 * That the two look alike is the reason `useRouteChecks` fails whole rather
 * than partially: within one render, either every row has been checked or none
 * has, so an unlabelled row means "ordinary" throughout, or the column is
 * empty throughout and means nothing at all.
 */

import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import {
  ROUTE_OUTCOME_LABEL,
  ROUTE_OUTCOME_VARIANT,
  routeDetailLines,
} from "../utils/financial-route"
import type { FileRoute } from "../hooks/use-route-checks"

interface RouteBadgeProps {
  /** Undefined when the file was not checked, or the check has not answered. */
  route: FileRoute | undefined
}

export function RouteBadge({ route }: RouteBadgeProps) {
  if (!route) return null
  // The one outcome that is deliberately unlabelled. See the header.
  if (route.outcome === "not_native") return null

  const { outcome } = route

  // Shared with the hold dialog rather than written here, so that the same
  // file cannot be explained one way on the list and another way in the dialog
  // that stops it being processed.
  const detail = routeDetailLines(route)

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant={ROUTE_OUTCOME_VARIANT[outcome]} className="text-[10px]">
          {ROUTE_OUTCOME_LABEL[outcome]}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        {detail.map((line) => (
          <p key={line} className="not-first:mt-1">
            {line}
          </p>
        ))}
      </TooltipContent>
    </Tooltip>
  )
}
