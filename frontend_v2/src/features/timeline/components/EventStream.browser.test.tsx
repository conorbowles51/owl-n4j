import { render } from "@testing-library/react"
import { expect, it } from "vitest"
import "@/styles/globals.css"
import { ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import type { TimelineEvent } from "../api"
import type { StreamItem } from "../hooks/use-filtered-events"
import { EventStream } from "./EventStream"

const event = (index: number): TimelineEvent => ({
  key: `event-${index}`,
  name: `Payment ${index}`,
  type: "Transaction",
  date: "2021-02-08",
  time: null,
  amount: null,
  summary: null,
  notes: null,
  connections: [],
})

it("renders only the visible rows of a long Timeline inside its panel", async () => {
  const items: StreamItem[] = [
    { kind: "header", date: "2021-02-08", label: "Mon, Feb 8, 2021", count: 3000 },
    ...Array.from({ length: 3000 }, (_, index) => ({ kind: "event" as const, event: event(index) })),
  ]
  const { container } = render(
    <div style={{ height: 600, display: "flex", flexDirection: "column" }}>
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        <ResizablePanel defaultSize="100">
          <EventStream
            items={items}
            totalCount={3000}
            selectedEventKey={null}
            multiSelectedKeys={new Set()}
            searchTerm=""
            selectedEntityKeys={new Set()}
            scrollToEventKey={null}
            onSelectEvent={() => {}}
            onMultiSelectEvent={() => {}}
            onClearScrollTarget={() => {}}
            onClearFilters={() => {}}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
  await new Promise((resolve) => setTimeout(resolve, 300))
  const rows = container.querySelectorAll("[data-index]")
  expect(rows.length).toBeGreaterThan(0)
  expect(rows.length).toBeLessThan(40)
  const scroller = rows[0].parentElement!.parentElement!
  expect(scroller.clientHeight).toBeLessThanOrEqual(600)
})
