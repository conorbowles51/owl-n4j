import type { Meta, StoryObj } from "@storybook/react-vite"
import { fn } from "@storybook/test"
import { EntityCard } from "@/components/ui/entity-card"
import type { EntityType } from "@/lib/theme"

const meta = {
  title: "@owl/ui/EntityCard",
  component: EntityCard,
  tags: ["autodocs"],
} satisfies Meta<typeof EntityCard>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    name: "John Smith",
    type: "person",
    connectionCount: 12,
  },
}

export const NoConnections: Story = {
  args: {
    name: "Unknown Entity",
    type: "organization",
  },
}

const sampleTypes: { type: EntityType; name: string }[] = [
  { type: "person", name: "John Smith" },
  { type: "organization", name: "Acme Corp" },
  { type: "location", name: "New York" },
  { type: "financial", name: "Account #4421" },
  { type: "document", name: "Report.pdf" },
  { type: "event", name: "Meeting 03/01" },
  { type: "communication", name: "Email Thread" },
  { type: "vehicle", name: "BMW X5" },
  { type: "digital", name: "192.168.1.1" },
  { type: "evidence", name: "Exhibit A" },
]

export const AllTypes = {
  render: () => (
    <div className="grid max-w-md gap-2">
      {sampleTypes.map(({ type, name }) => (
        <EntityCard key={type} type={type} name={name} connectionCount={5} />
      ))}
    </div>
  ),
}

export const Clickable: Story = {
  args: {
    name: "Jane Doe",
    type: "person",
    connectionCount: 7,
    onClick: fn(),
  },
}
