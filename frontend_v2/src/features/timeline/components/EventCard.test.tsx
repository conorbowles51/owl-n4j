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

function withEvent(extra: Partial<TimelineEvent>) {
  const event: TimelineEvent = {
    key: "e2", name: "Transfer From Somebody", type: "Transaction", date: "2021-02-08", time: null,
    amount: "1,200.00", summary: null, notes: null, connections: [], ...extra,
  }
  return render(
    <EventCard event={event} isSelected={false} isMultiSelected={false} searchTerm=""
      highlightedEntityKeys={new Set()} onSelect={() => {}} onMultiSelect={() => {}} />
  )
}

// lx-style (Neil 2 Nov): money in / out comes from the payment's own direction, never its title.
it("marks money in and out from the payment's direction field, not its title", () => {
  const { unmount } = withEvent({ name: "Transfer From Somebody", direction: "debit" })
  expect(screen.getByText("↑ out")).toBeTruthy()
  expect(screen.getByText("1,200.00").className).toContain("text-money-out")
  unmount()
  withEvent({ name: "Payment To Somebody", direction: "credit" })
  expect(screen.getByText("↓ in")).toBeTruthy()
  expect(screen.getByText("1,200.00").className).toContain("text-money-in")
})

it("shows no in/out mark without a direction, and a known amount in the info colour", () => {
  withEvent({ name: "Transfer To Somebody" })
  expect(screen.queryByText("↑ out")).toBeNull()
  expect(screen.queryByText("↓ in")).toBeNull()
  expect(screen.getByText("1,200.00").className).toContain("text-status-info")
})

it("turns an unknown amount into a check tag with words, and edges the card in its type colour", () => {
  const { container } = withEvent({ amount: "unknown" })
  expect(screen.getByText("Amount unknown · check source")).toBeTruthy()
  const article = container.querySelector("article") as HTMLElement
  expect(article.style.borderLeftColor).not.toBe("")
})

// lx-demo 10 Nov: the document model's events sat beside the ledger's rows with nothing saying who wrote them.
it("labels an event the document model wrote as a model reading with its file, and a ledger row not", () => {
  const { unmount } = withEvent({ source_files: ["bay4-lease-2023-10-01.pdf"] })
  expect(screen.getByText("Model reading, not checked · bay4-lease-2023-10-01.pdf")).toBeTruthy()
  unmount()
  const { unmount: u2 } = withEvent({ source_files: ["a.pdf", "b.pdf", "c.pdf"] })
  expect(screen.getByText("Model reading, not checked · a.pdf and 2 more")).toBeTruthy()
  u2()
  const { container, unmount: u3 } = withEvent({ source_files: null, ledger_transaction_id: "t1" })
  expect(container.querySelector("[data-model-reading]")).toBeNull()
  u3()
  const { container: c4 } = withEvent({ source_files: ["shop.pdf"], ledger_transaction_id: "t1" })
  expect(c4.querySelector("[data-model-reading]")).toBeNull()
})

// lx-photos: a photo's event shows the picture, says its date is the photo's own data, and shows attached files.
it("shows a photo's thumbnail and words its date as the photo's data, not checked", () => {
  const event: TimelineEvent = {
    key: "photo:1", name: "Photo taken", type: "Photo", date: "2024-05-01", time: "12:30", amount: null,
    summary: "a.jpg", notes: null, connections: [], thumbnail_url: "/api/photos/1/thumbnail?case_id=c",
    source: { kind: "evidence_file", id: "1", label: "a.jpg", state: "current",
      date_basis: "From the photo's data, not checked by a person. Time zone not recorded." },
  }
  const { container } = render(
    <EventCard event={event} isSelected={false} isMultiSelected={false} searchTerm=""
      highlightedEntityKeys={new Set()} onSelect={() => {}} onMultiSelect={() => {}} />
  )
  expect(container.querySelector('img[src="/api/photos/1/thumbnail?case_id=c"]')).not.toBeNull()
  expect(screen.getByText(/not checked by a person/)).toBeTruthy()
})

it("shows the files attached to an event, with who attached them", () => {
  const event: TimelineEvent = {
    key: "e9", name: "Meeting", type: "Event", date: "2024-05-01", time: null, amount: null, summary: null,
    notes: null, connections: [],
  }
  const { container } = render(
    <EventCard event={event} isSelected={false} isMultiSelected={false} searchTerm=""
      highlightedEntityKeys={new Set()} onSelect={() => {}} onMultiSelect={() => {}}
      attachedFiles={[{ id: "f", event_key: "e9", evidence_file_id: "1", name: "b.jpg", added_by: "x@y.z",
        thumbnail_url: "/api/photos/1/thumbnail?case_id=c" }]} />
  )
  expect(container.querySelector('[data-event-files] img[title="b.jpg, attached by x@y.z"]')).not.toBeNull()
})
