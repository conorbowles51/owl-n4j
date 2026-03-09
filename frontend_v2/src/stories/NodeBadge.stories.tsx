import type { Meta, StoryObj } from "@storybook/react-vite"
import { NodeBadge } from "@/components/ui/node-badge"
import type { EntityType } from "@/lib/theme"

const meta = {
  title: "@owl/ui/NodeBadge",
  component: NodeBadge,
  tags: ["autodocs"],
} satisfies Meta<typeof NodeBadge>

export default meta
type Story = StoryObj<typeof meta>

const allTypes: EntityType[] = [
  "person",
  "organization",
  "location",
  "financial",
  "document",
  "event",
  "communication",
  "vehicle",
  "digital",
  "evidence",
]

export const AllTypes = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {allTypes.map((type) => (
        <NodeBadge key={type} type={type} />
      ))}
    </div>
  ),
}

export const CustomLabel: Story = {
  args: {
    type: "person",
    children: "John Doe",
  },
}
