import type { Meta, StoryObj } from "@storybook/react-vite"
import { PageHeader } from "../page-header"
import { Card, CardDescription, CardHeader, CardTitle } from "../card"
import { Label } from "../label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../table"

/** lx-style E and F: page title, section, label, eyebrow and data; dense and comfortable tables; card elevation. */
const meta = { title: "Style/Type and density", parameters: { layout: "fullscreen" } } satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const rows = [
  ["3 Mar 2024", "Transfer to Wren Pennywhistle", "390.02"],
  ["10 Mar 2024", "Card payment, Synthetic Grocers", "1,204.50"],
  ["11 Mar 2024", "Transfer from Northcott Storage Ltd", "88,332.71"],
]

const sample = (density: "dense" | "comfortable") => (
  <Table density={density} aria-label={`${density} table`}>
    <TableHeader>
      <TableRow>
        <TableHead>Description</TableHead>
        <TableHead className="text-right">Amount</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {rows.map(([d, t, a]) => (
        <TableRow key={t}>
          <TableCell className="whitespace-normal">
            <span className="block">{t}</span>
            <span className="type-eyebrow text-muted-foreground">{d}</span>
          </TableCell>
          <TableCell className="text-right">{a}</TableCell>
        </TableRow>
      ))}
    </TableBody>
  </Table>
)

const Scale = () => (
  <main className="flex flex-col gap-stack-reading bg-background p-panel-reading text-foreground">
    <PageHeader title="Statements and accounts" description="Every statement read for this case." />
    <p className="type-eyebrow text-muted-foreground">Source · page 3 · row 14</p>
    <div className="grid grid-cols-1 gap-stack">
      <Card>
        <CardHeader>
          <CardTitle>Dense: tables to compare</CardTitle>
          <CardDescription>Rows of 32 px.</CardDescription>
        </CardHeader>
        {sample("dense")}
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Comfortable: everything else</CardTitle>
          <CardDescription>Rows of 40 px.</CardDescription>
        </CardHeader>
        {sample("comfortable")}
      </Card>
    </div>
    <div className="flex flex-col gap-1">
      <Label htmlFor="holder">Account holder</Label>
      <input id="holder" className="rounded-md border border-input bg-card px-2 py-1" defaultValue="Emrys Juniper" />
    </div>
  </main>
)

export const ScaleLight: Story = { render: Scale, parameters: { theme: "light" } }
export const ScaleDark: Story = { render: Scale, parameters: { theme: "dark" } }
