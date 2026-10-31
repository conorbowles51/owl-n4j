import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import type { TimelineEvent } from "../api"
import { EventCard } from "./EventCard"

function card(amount: TimelineEvent["amount"]) {
  const event: TimelineEvent = {
    key: "e1", name: "Payment to supplier", type: "Transaction", date: "2021-02-08", time: null,
    amount, summary: null, notes: null, connections: [],
  }
  return render(
    <EventCard event={event} isSelected={false} isMultiSelected={false} searchTerm=""
      highlightedEntityKeys={new Set()} onSelect={() => {}} onMultiSelect={() => {}} />
  )
}

// Live (0488875d) has 4 events whose stored amount is the number 0; the card printed a bare "0"
// outside the amount label instead of the amount.
it("shows a zero amount in the amount label, like any other amount", () => {
  card(0)
  const label = screen.getByText("0")
  expect(label.className).toContain("font-semibold")
})

it("shows numeric and text amounts, and nothing for a missing or blank amount", () => {
  const { unmount } = card(125000.5)
  expect(screen.getByText("125000.5").className).toContain("font-semibold")
  unmount()
  for (const none of [null, ""] as const) {
    const { container, unmount: u } = card(none)
    expect(container.querySelector(".font-semibold.shrink-0")).toBeNull()
    u()
  }
})
