import type { Meta, StoryObj } from "@storybook/react-vite"
import { LoadingSpinner } from "@/components/ui/loading-spinner"

const meta = {
  title: "@owl/ui/LoadingSpinner",
  component: LoadingSpinner,
  tags: ["autodocs"],
} satisfies Meta<typeof LoadingSpinner>

export default meta
type Story = StoryObj<typeof meta>

export const AllSizes: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <LoadingSpinner size="sm" />
      <LoadingSpinner size="default" />
      <LoadingSpinner size="lg" />
    </div>
  ),
}
