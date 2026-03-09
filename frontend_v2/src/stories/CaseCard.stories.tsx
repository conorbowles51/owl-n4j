import type { Meta, StoryObj } from "@storybook/react-vite"
import { fn } from "@storybook/test"
import { CaseCard } from "@/components/ui/case-card"

const meta = {
  title: "@owl/ui/CaseCard",
  component: CaseCard,
  tags: ["autodocs"],
} satisfies Meta<typeof CaseCard>

export default meta
type Story = StoryObj<typeof meta>

export const Active: Story = {
  args: {
    name: "Operation Falcon",
    status: "active",
    memberCount: 4,
    lastUpdated: "2 hours ago",
  },
}

export const Archived: Story = {
  args: {
    name: "Case #2021-0042",
    status: "archived",
    memberCount: 2,
    lastUpdated: "3 months ago",
  },
}

export const Closed: Story = {
  args: {
    name: "Investigation Delta",
    status: "closed",
    memberCount: 6,
    lastUpdated: "1 year ago",
  },
}

export const WithDescription: Story = {
  args: {
    name: "Operation Falcon",
    description: "Cross-border financial fraud investigation involving multiple shell companies.",
    status: "active",
    memberCount: 4,
    lastUpdated: "2 hours ago",
  },
}

export const Clickable: Story = {
  args: {
    name: "Operation Falcon",
    status: "active",
    memberCount: 4,
    lastUpdated: "2 hours ago",
    onClick: fn(),
  },
}
