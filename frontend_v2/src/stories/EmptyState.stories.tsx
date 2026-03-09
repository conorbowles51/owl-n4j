import type { Meta, StoryObj } from "@storybook/react-vite"
import { EmptyState } from "@/components/ui/empty-state"
import { Button } from "@/components/ui/button"
import { FileQuestion } from "lucide-react"

const meta = {
  title: "@owl/ui/EmptyState",
  component: EmptyState,
  tags: ["autodocs"],
} satisfies Meta<typeof EmptyState>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    title: "No items found",
  },
}

export const WithIcon: Story = {
  args: {
    icon: FileQuestion,
    title: "No documents",
    description: "Upload a document to get started with your investigation.",
  },
}

export const WithAction: Story = {
  args: {
    title: "No cases yet",
    description: "Create your first case to begin an investigation.",
    action: <Button size="sm">Create Case</Button>,
  },
}

export const Full: Story = {
  args: {
    icon: FileQuestion,
    title: "No results found",
    description: "Try adjusting your search or filters to find what you're looking for.",
    action: (
      <Button variant="outline" size="sm">
        Clear Filters
      </Button>
    ),
  },
}
