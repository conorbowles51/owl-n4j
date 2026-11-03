import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import type { TimelineEvent } from "../api"
import { UndatedEvents } from "./UndatedEvents"

it("lists events with no usable date with their count instead of dropping them (03 section 15.6)", () => {
  const ev = (key: string, date: string | null) => ({ key, name: `Synthetic ${key}`, type: "Payment", date, time: null, summary: null }) as unknown as TimelineEvent
  render(<UndatedEvents events={[ev("a", null), ev("b", "not a date")]} />)
  expect(screen.getByText("No time recorded: 2 events have no usable date")).toBeInTheDocument()
  expect(screen.getByText("Synthetic a")).toBeInTheDocument()
  expect(screen.getByText(/date as entered: not a date/)).toBeInTheDocument()
})
