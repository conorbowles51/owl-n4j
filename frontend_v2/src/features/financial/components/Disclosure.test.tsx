import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { Disclosure } from "./Disclosure"

afterEach(cleanup)

it("starts closed or open, reports each toggle, and keeps its label as the button name", () => {
  const onToggle = vi.fn()
  render(
    <>
      <Disclosure label="All financial cases" onToggle={onToggle}>
        <p>Case list</p>
      </Disclosure>
      <Disclosure label="Open by default" defaultOpen>
        <p>Shown</p>
      </Disclosure>
    </>
  )
  const cases = screen.getByRole("button", { name: /All financial cases/ })
  expect(cases).toHaveAttribute("aria-expanded", "false")
  expect(screen.getByText("Case list").parentElement).toHaveClass("hidden")
  fireEvent.click(cases)
  expect(cases).toHaveAttribute("aria-expanded", "true")
  expect(onToggle).toHaveBeenLastCalledWith(true)
  fireEvent.click(cases)
  expect(onToggle).toHaveBeenLastCalledWith(false)
  expect(screen.getByRole("button", { name: /Open by default/ })).toHaveAttribute("aria-expanded", "true")
  expect(screen.getByText("Shown").parentElement).not.toHaveClass("hidden")
})
