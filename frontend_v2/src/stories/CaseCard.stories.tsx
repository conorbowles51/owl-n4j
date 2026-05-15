import type { Meta, StoryObj } from "@storybook/react-vite"
import { fn } from "storybook/test"
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
    title: "Operation Falcon",
    userRole: "owner",
    ownerName: "Avery Stone",
    lastUpdated: new Date().toISOString(),
  },
}

export const Archived: Story = {
  args: {
    title: "Case #2021-0042",
    userRole: "viewer",
    ownerName: "Neil Byrne",
    lastUpdated: new Date().toISOString(),
  },
}

export const Closed: Story = {
  args: {
    title: "Investigation Delta",
    userRole: "editor",
    ownerName: "Mara Chen",
    lastUpdated: new Date().toISOString(),
  },
}

export const WithDescription: Story = {
  args: {
    title: "Operation Falcon",
    description: "Cross-border financial fraud investigation involving multiple shell companies.",
    userRole: "owner",
    ownerName: "Avery Stone",
    lastUpdated: new Date().toISOString(),
  },
}

export const Clickable: Story = {
  args: {
    title: "Operation Falcon",
    userRole: "owner",
    ownerName: "Avery Stone",
    lastUpdated: new Date().toISOString(),
    onClick: fn(),
  },
}
