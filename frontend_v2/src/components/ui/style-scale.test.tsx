// lx-style E and F: the type scale, density and elevation live in the theme and the shared primitives.
import { readFileSync } from "node:fs"
import path from "node:path"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { PageHeader } from "./page-header"
import { Card, CardTitle } from "./card"
import { Label } from "./label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table"

const css = readFileSync(path.resolve(__dirname, "../../styles/globals.css"), "utf8")

describe("type scale (lx-style E)", () => {
  it("defines one utility per role", () => {
    for (const role of ["type-page", "type-section", "type-label", "type-eyebrow", "type-data"])
      expect(css).toContain(`@utility ${role} {`)
    expect(css).toMatch(/@utility type-page \{\s*font-family: var\(--font-display\)/)
    expect(css).toMatch(/@utility type-section \{\s*font-family: var\(--font-display\)/)
    expect(css).toMatch(/@utility type-eyebrow \{\s*font-family: var\(--font-mono\)/)
  })
  it("figures are tabular across the app", () => {
    expect(css).toMatch(/body \{[^}]*font-variant-numeric: tabular-nums;/)
  })
  it("the shared primitives use the scale", () => {
    render(
      <>
        <PageHeader title="Cases" />
        <Card>
          <CardTitle>Accounts</CardTitle>
        </Card>
        <Label>Holder</Label>
      </>
    )
    expect(screen.getByRole("heading", { name: "Cases" }).className).toContain("type-page")
    expect(screen.getByText("Accounts").className).toContain("type-section")
    expect(screen.getByText("Holder").className).toContain("type-label")
  })
})

describe("density and elevation (lx-style F)", () => {
  it("defines spacing tokens for dense tables and reading panels", () => {
    for (const t of ["cell", "cell-dense", "row", "row-dense", "panel", "panel-reading", "stack", "stack-reading"])
      expect(css).toMatch(new RegExp(`--spacing-${t}: [0-9.]+rem;`))
  })
  it("tables are comfortable by default and dense on request, from the tokens", () => {
    const table = (density?: "dense") => (
      <Table density={density} aria-label={density ?? "default"}>
        <TableHeader>
          <TableRow>
            <TableHead>Amount</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>1,204.50</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )
    render(
      <>
        {table()}
        {table("dense")}
      </>
    )
    const [comfortable, dense] = screen.getAllByRole("table")
    expect(comfortable).toHaveAttribute("data-density", "comfortable")
    expect(dense).toHaveAttribute("data-density", "dense")
    expect(comfortable.className).toContain("type-data")
    expect(screen.getAllByText("1,204.50")[0].className).toContain("p-cell")
    expect(screen.getAllByText("Amount")[0].className).toContain("h-row")
    expect(screen.getAllByText("1,204.50")[1].className).toContain("in-data-[density=dense]:py-cell-dense")
    expect(screen.getAllByText("Amount")[1].className).toContain("in-data-[density=dense]:h-row-dense")
  })
  it("cards step off the page by elevation in light and dark, not by a border alone", () => {
    render(<Card data-testid="card" />)
    expect(screen.getByTestId("card").className).toContain("shadow-[var(--elev-raised)]")
    expect(css).toMatch(/:root \{\s*--elev-raised:/)
    expect(css).toMatch(/\.dark \{\s*--elev-raised:/)
  })
})
