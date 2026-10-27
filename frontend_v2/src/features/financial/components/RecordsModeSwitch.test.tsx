import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { RecordsModeSwitch } from "./RecordsModeSwitch"

afterEach(cleanup)

it("switches records and pins the explanation open on click instead of hover only", () => {
  const onChange = vi.fn()
  render(<RecordsModeSwitch transactionsMode onChange={onChange} />)
  expect(screen.getByRole("button", { name: "Statement payments" })).toHaveAttribute("aria-pressed", "true")
  fireEvent.click(screen.getByRole("button", { name: "Other financial records" }))
  expect(onChange).toHaveBeenCalledWith("intelligence")
  fireEvent.click(screen.getByRole("button", { name: /^About this: Statement payments come from imported/ }))
  expect(screen.getByRole("note")).toHaveTextContent("correcting a statement payment does not change them")
})
