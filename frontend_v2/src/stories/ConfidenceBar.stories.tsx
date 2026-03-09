import type { Meta, StoryObj } from "@storybook/react-vite"
import { ConfidenceBar } from "@/components/ui/confidence-bar"

const meta = {
  title: "@owl/ui/ConfidenceBar",
  component: ConfidenceBar,
  tags: ["autodocs"],
} satisfies Meta<typeof ConfidenceBar>

export default meta
type Story = StoryObj<typeof meta>

export const High: Story = {
  args: {
    value: 0.92,
  },
}

export const Medium: Story = {
  args: {
    value: 0.65,
  },
}

export const Low: Story = {
  args: {
    value: 0.3,
  },
}

export const VeryLow: Story = {
  args: {
    value: 0.15,
  },
}

export const NoLabel: Story = {
  args: {
    value: 0.65,
    showLabel: false,
  },
}

export const AllLevels = {
  render: () => (
    <div className="flex max-w-sm flex-col gap-3">
      <ConfidenceBar value={0.95} />
      <ConfidenceBar value={0.75} />
      <ConfidenceBar value={0.50} />
      <ConfidenceBar value={0.30} />
      <ConfidenceBar value={0.15} />
    </div>
  ),
}
