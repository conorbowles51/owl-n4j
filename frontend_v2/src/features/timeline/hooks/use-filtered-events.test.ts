import { renderHook } from "@testing-library/react"
import { expect, it } from "vitest"
import type { TimelineEvent } from "../api"
import { useFilteredEvents } from "./use-filtered-events"

function event(key: string, connections: TimelineEvent["connections"]): TimelineEvent {
  return {
    key,
    name: `Payment ${key}`,
    type: "Transaction",
    date: "2021-02-08",
    time: null,
    amount: null,
    summary: null,
    notes: null,
    connections,
  }
}

const events: TimelineEvent[] = [
  // Live data has statement periods with no name at all (49494305: 9 after the server names the rest).
  event("a", [
    { key: "p", name: null as unknown as string, type: "FinancialStatementPeriod", relationship: "IN_PERIOD", direction: "outgoing" },
  ]),
  event("b", [
    { key: "acc", name: "ARRENDO SERV SA DE CV · Monex · 2836625 · MXN", type: "FinancialAccount", relationship: "FROM", direction: "incoming" },
  ]),
]

function search(term: string) {
  const { result } = renderHook(() =>
    useFilteredEvents({
      events,
      selectedTypes: new Set(),
      selectedEntityKeys: new Set(),
      dateRange: { start: null, end: null },
      visibleWindow: null,
      searchTerm: term,
    })
  )
  return result.current.filteredEvents.map((e) => e.key)
}

it("search does not stop on a connection with no name, and finds it by the type the page shows", () => {
  expect(search("monex")).toEqual(["b"])
  expect(search("financialstatementperiod")).toEqual(["a"])
})
