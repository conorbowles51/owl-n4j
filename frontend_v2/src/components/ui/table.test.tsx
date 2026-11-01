import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, expect, it } from "vitest"
import { Table, TableBody, TableCell, TableRow } from "./table"

// lx-style 1 Nov, measured live the same day: the Evidence list's table overflows its panel at 1024 and 768 px wide,
// and its scroll area could not take focus, so it could not be scrolled sideways without a mouse.
const descriptors = {
  scrollWidth: Object.getOwnPropertyDescriptor(Element.prototype, "scrollWidth")!,
  clientWidth: Object.getOwnPropertyDescriptor(Element.prototype, "clientWidth")!,
}
beforeEach(() => {
  for (const key of ["scrollWidth", "clientWidth"] as const)
    Object.defineProperty(Element.prototype, key, {
      configurable: true,
      get(this: Element) {
        return Number(this.closest("[data-test-wide]") && this.getAttribute("data-slot") === "table-container"
          ? { scrollWidth: 900, clientWidth: 400 }[key]
          : 0)
      },
    })
})
afterEach(() => {
  for (const [key, descriptor] of Object.entries(descriptors)) Object.defineProperty(Element.prototype, key, descriptor)
})

const rows = (
  <TableBody>
    <TableRow>
      <TableCell>a</TableCell>
    </TableRow>
  </TableBody>
)

it("lets the keyboard reach a table wider than its panel, named after the table", () => {
  render(
    <div data-test-wide>
      <Table aria-label="Evidence files">{rows}</Table>
    </div>
  )
  const region = screen.getByRole("region", { name: "Evidence files" })
  expect(region.getAttribute("tabindex")).toBe("0")
  expect(region.getAttribute("data-slot")).toBe("table-container")
})

it("names an overflowing table without a label after its caption, or plainly", () => {
  render(
    <div data-test-wide>
      <Table>
        <caption>Statement periods</caption>
        {rows}
      </Table>
    </div>
  )
  expect(screen.getByRole("region", { name: "Statement periods" })).toBeTruthy()
})

it("adds no tab stop or region to a table that fits", () => {
  const { container } = render(<Table aria-label="Fits">{rows}</Table>)
  const area = container.querySelector("[data-slot=table-container]")!
  expect(area.hasAttribute("tabindex")).toBe(false)
  expect(screen.queryByRole("region")).toBeNull()
})

it("names an overflowing table's region by the elements that label the table", () => {
  render(
    <div data-test-wide>
      <h2 id="payments-heading">Payments</h2>
      <Table aria-labelledby="payments-heading">{rows}</Table>
    </div>
  )
  const region = screen.getByRole("region", { name: "Payments" })
  expect(region.getAttribute("aria-labelledby")).toBe("payments-heading")
  expect(region.hasAttribute("aria-label")).toBe(false)
})
