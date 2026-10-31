import { render } from "@testing-library/react"
import { expect, it } from "vitest"
import "@/styles/globals.css"
import type { DerivedEntity } from "../lib/timeline-utils"
import { FilterSidebar } from "./FilterSidebar"

// A long company name as it appears in a real case's entity list, a short one, and large counts.
const entities: DerivedEntity[] = [
  { key: "a", name: "ECOTERRA SERVICIOS AMBIENTALES SA DE CV", type: "FinancialAccount" as DerivedEntity["type"], eventCount: 4699 },
  { key: "b", name: "METALMEX ENERGIA Y SUSTENTO SA DE CV", type: "FinancialAccount" as DerivedEntity["type"], eventCount: 2322 },
  { key: "c", name: "ARRENDO SERV", type: "FinancialAccount" as DerivedEntity["type"], eventCount: 172 },
]

const overlaps = (a: DOMRect, b: DOMRect) =>
  a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom && b.top < a.bottom

function renderAt(width: number) {
  return render(
    <div style={{ width, height: 600 }}>
      <FilterSidebar
        eventTypes={["FinancialTransaction"]}
        selectedTypes={new Set(["FinancialTransaction"])}
        onToggleType={() => {}}
        onSelectAllTypes={() => {}}
        onClearAllTypes={() => {}}
        entities={entities}
        selectedEntityKeys={new Set()}
        entityFilterCounts={new Map([["a", 4699], ["b", 2322], ["c", 172]])}
        onToggleEntity={() => {}}
        onClearEntityFilter={() => {}}
        onFocusEntity={() => {}}
        activeFilterCount={0}
        onClearAll={() => {}}
      />
    </div>
  )
}

// 240 px is the panel's width at 1600 px; 176 px at 1280 px (both measured on the live Timeline).
for (const width of [240, 176]) {
  it(`long entity names never draw over their count or the Focus button at ${width}px`, async () => {
    const { container } = renderAt(width)
    await new Promise((resolve) => setTimeout(resolve, 50))
    // Rows are found by their Focus button, so the same checks run against any markup of the row.
    const focusButtons = Array.from(container.querySelectorAll("button")).filter((b) => b.textContent === "Focus")
    const rows = focusButtons.map((b) => b.parentElement as HTMLElement)
    expect(rows).toHaveLength(3)
    for (const row of rows) {
      const entity = entities.find((e) => row.textContent?.includes(e.name))!
      const label = row.querySelector("label")!
      const spans = Array.from(label.querySelectorAll<HTMLElement>(":scope > span"))
      const badge = spans[0]
      const count = spans[spans.length - 1]
      const focus = row.querySelector("button")!
      const R = row.getBoundingClientRect()
      const B = badge.getBoundingClientRect()
      const N = count.getBoundingClientRect()
      const F = focus.getBoundingClientRect()
      expect(overlaps(B, N), `${entity.name}: name over count`).toBe(false)
      expect(overlaps(B, F), `${entity.name}: name over Focus`).toBe(false)
      expect(overlaps(N, F), `${entity.name}: count over Focus`).toBe(false)
      expect(F.right).toBeLessThanOrEqual(R.right + 0.5)
      const name = row.querySelector<HTMLElement>("[data-entity-name]")
      expect(name, "name has its own truncating box").not.toBeNull()
      // The name text is either fully shown or clipped with an ellipsis inside its own box.
      const style = getComputedStyle(name!)
      if (name!.scrollWidth > name!.clientWidth + 1) {
        expect(style.textOverflow).toBe("ellipsis")
        expect(style.overflow).toBe("hidden")
      }
      expect(name!.getBoundingClientRect().right).toBeLessThanOrEqual(B.right + 0.5)
      // Nothing is hidden without a way to read it: the full name is in the row's tooltip.
      expect(label.getAttribute("title")).toBe(entity.name)
      expect(count.textContent).toBe(String(entity.eventCount))
    }
    // The long names really are clipped at this width (otherwise the test proves nothing).
    const clipped = rows.filter((r) => {
      const n = r.querySelector<HTMLElement>("[data-entity-name]")!
      return n.scrollWidth > n.clientWidth + 1
    })
    expect(clipped.length).toBeGreaterThan(0)
  })
}
