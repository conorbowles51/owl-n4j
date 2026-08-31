/**
 * What the badge says, and — mostly — when it says nothing.
 *
 * The silence is the part worth testing. A badge on every row is a column
 * nobody reads, so an ordinary document is deliberately unlabelled; that
 * decision is only safe while the label, when it does appear, is never wrong.
 */

import type { ReactElement } from "react"
import { render as renderBare, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { TooltipProvider } from "@/components/ui/tooltip"
import { RouteBadge } from "./RouteBadge"
import type { FileRoute } from "../hooks/use-route-checks"
import {
  ALL_ROUTE_OUTCOMES,
  ROUTE_OUTCOME_LABEL,
  ROUTE_OUTCOME_VARIANT,
  type RouteOutcome,
} from "../utils/financial-route"

function route(overrides: Partial<FileRoute> & { outcome: RouteOutcome }): FileRoute {
  return {
    file_id: "f1",
    file_name: "statement.dat",
    claimants: [],
    detected_format: null,
    blocks_document_processing: false,
    reason: null,
    ...overrides,
  }
}

/**
 * The badge lives in a tooltip, which radix requires a provider for.
 *
 * The application supplies one in `app/providers.tsx` and `EvidenceExplorer`
 * supplies another, so this mirrors the tree the component really renders in
 * rather than working around the requirement.
 */
function render(ui: ReactElement) {
  return renderBare(<TooltipProvider>{ui}</TooltipProvider>)
}

/**
 * Found by printing the rendered DOM rather than by reading radix: a
 * `TooltipTrigger asChild` merges its own props onto the child it wraps, and
 * its `data-slot="tooltip-trigger"` replaces the badge's `data-slot="badge"`.
 * `data-variant` is the badge's alone and survives, so it is what identifies
 * the element here. Nothing in the codebase selects on `data-slot="badge"`
 * (checked), so the override costs nothing outside this file.
 */
function badge() {
  return document.querySelector("[data-variant]")
}

describe("RouteBadge", () => {
  it("says nothing for a file that was not checked", () => {
    render(<RouteBadge route={undefined} />)
    expect(badge()).toBeNull()
  })

  it("says nothing for an ordinary document", () => {
    // The common case, and the reason the badge is legible at all: on a list of
    // a thousand files, a label on the 999 uninteresting ones hides the one.
    render(<RouteBadge route={route({ outcome: "not_native" })} />)
    expect(badge()).toBeNull()
  })

  it("names a bank file", () => {
    render(<RouteBadge route={route({ outcome: "native", detected_format: "camt053" })} />)
    expect(screen.getByText(ROUTE_OUTCOME_LABEL.native)).toBeInTheDocument()
  })

  it("labels every outcome that is not an ordinary document", () => {
    // Written against the union rather than a list repeated here, so that an
    // outcome added to `financial-route.ts` cannot quietly render nothing.
    for (const outcome of ALL_ROUTE_OUTCOMES) {
      if (outcome === "not_native") continue
      const { unmount } = render(<RouteBadge route={route({ outcome })} />)
      expect(
        screen.getByText(ROUTE_OUTCOME_LABEL[outcome]),
        `${outcome} renders no label`
      ).toBeInTheDocument()
      unmount()
    }
  })

  it("colours each outcome the way the shared table says", () => {
    for (const outcome of ALL_ROUTE_OUTCOMES) {
      if (outcome === "not_native") continue
      const { unmount } = render(<RouteBadge route={route({ outcome })} />)
      expect(badge()?.getAttribute("data-variant"), `${outcome} has the wrong variant`).toBe(
        ROUTE_OUTCOME_VARIANT[outcome]
      )
      unmount()
    }
  })

  it("never renders an empty label", () => {
    // The failure this is guarding against is a `Record` lookup returning
    // undefined for an outcome the service knows and this build does not.
    // `useRouteChecks` narrows before the badge sees it, so the badge should
    // never be blank -- but a blank badge looks like an answer, so it is worth
    // asserting rather than assuming.
    for (const outcome of ALL_ROUTE_OUTCOMES) {
      if (outcome === "not_native") continue
      const { unmount } = render(<RouteBadge route={route({ outcome })} />)
      expect(badge()?.textContent?.trim(), `${outcome} renders a blank badge`).toBeTruthy()
      unmount()
    }
  })
})
