import type { Meta, StoryObj } from "@storybook/react-vite"
import { PresenceIndicator } from "@/components/ui/presence-indicator"

const meta = {
  title: "@owl/ui/PresenceIndicator",
  component: PresenceIndicator,
  tags: ["autodocs"],
} satisfies Meta<typeof PresenceIndicator>

export default meta
type Story = StoryObj<typeof meta>

export const FewUsers: Story = {
  args: {
    users: [
      { name: "Alice Morgan", initials: "AM" },
      { name: "Bob Chen", initials: "BC" },
    ],
  },
}

export const ManyUsers: Story = {
  args: {
    users: [
      { name: "Alice Morgan", initials: "AM" },
      { name: "Bob Chen", initials: "BC" },
      { name: "Carol Davis", initials: "CD" },
      { name: "Dan Evans", initials: "DE" },
      { name: "Eve Foster", initials: "EF" },
    ],
    maxVisible: 3,
  },
}

export const SingleUser: Story = {
  args: {
    users: [{ name: "Alice Morgan", initials: "AM" }],
  },
}
