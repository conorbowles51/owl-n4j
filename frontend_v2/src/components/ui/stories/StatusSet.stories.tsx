import type { Meta, StoryObj } from "@storybook/react-vite"
import { Badge } from "../badge"

/** lx-style D: the semantic status set as badges, beside the phone kit's own statuses. Light and dark. */
const meta = { title: "Style/Status set", parameters: { layout: "padded" } } satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const Set = () => (
  <main className="flex flex-col gap-3 bg-background p-4 text-foreground">
    <div className="flex flex-wrap gap-2">
      <Badge variant="info">Info · 12 new files</Badge>
      <Badge variant="success">Balances reconcile</Badge>
      <Badge variant="danger">Could not be read</Badge>
      <Badge variant="slate">Set aside</Badge>
    </div>
    <div className="flex flex-wrap gap-2 bg-card p-2">
      <Badge variant="info">Info</Badge>
      <Badge variant="success">Success</Badge>
      <Badge variant="danger">Error</Badge>
      <Badge variant="slate">Neutral</Badge>
      <span className="rounded-sm bg-status-review-soft px-2 py-0.5 text-xs font-semibold text-status-review">Not yet confirmed</span>
      <span className="rounded-sm bg-status-model-soft px-2 py-0.5 text-xs font-semibold text-status-model">Machine-generated</span>
    </div>
  </main>
)

export const StatusLight: Story = { render: Set, parameters: { theme: "light" } }
export const StatusDark: Story = { render: Set, parameters: { theme: "dark" } }
