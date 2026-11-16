import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { asksForDeep, deepLine, looksBroad, type DeepProgress } from "../deep-investigation"
import { DeepChecklist } from "./DeepChecklist"

const progress: DeepProgress = {
  domain: "phones",
  total: 3,
  closed: 1,
  open: 2,
  not_done: 1,
  notes: 4,
  items: [
    { id: "a", title: "Every phone", status: "in_progress", covered: 2, of: 3 },
    { id: "b", title: "Media", status: "not_done", reason: "no media in the case", covered: 0, of: null },
    { id: "c", title: "Incidents", status: "done", covered: 0, of: null },
  ],
}

describe("deep investigation", () => {
  it("shows the true counts and the reason an item was not done", () => {
    render(<DeepChecklist progress={progress} />)
    expect(screen.getByTestId("deep-checklist-line").textContent).toBe(deepLine(progress))
    expect(screen.getByTestId("deep-checklist-line").textContent).toContain("1 of 3 checklist items closed, 2 items open; 4 findings noted.")
    expect(screen.getByText(/Every phone \(2 of 3\)/)).toBeTruthy()
    expect(screen.getByText(/not done, no media in the case/)).toBeTruthy()
  })

  it("starts on a request for a detailed report and offers it for a broad question", () => {
    expect(asksForDeep("Give me a detailed report about the phones in this case")).toBe(true)
    expect(asksForDeep("who called whom on Friday")).toBe(false)
    expect(looksBroad("Give me an overview of every phone in this case and who owns each one")).toBe(true)
    expect(looksBroad("Give me a detailed report about the phones in this case")).toBe(false)
  })
})
