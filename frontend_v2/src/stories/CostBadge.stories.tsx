import type { Meta, StoryObj } from "@storybook/react-vite"
import { CostBadge } from "@/components/ui/cost-badge"

const meta = {
  title: "@owl/ui/CostBadge",
  component: CostBadge,
  tags: ["autodocs"],
} satisfies Meta<typeof CostBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Small: Story = {
  args: {
    amount: 0.0023,
  },
}

export const Medium: Story = {
  args: {
    amount: 1.5,
  },
}

export const Large: Story = {
  args: {
    amount: 156.78,
  },
}

export const EUR: Story = {
  args: {
    amount: 42.99,
    currency: "EUR",
  },
}
