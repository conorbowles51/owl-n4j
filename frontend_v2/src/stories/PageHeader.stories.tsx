import type { Meta, StoryObj } from "@storybook/react-vite"
import { PageHeader } from "@/components/ui/page-header"
import { Button } from "@/components/ui/button"

const meta = {
  title: "@owl/ui/PageHeader",
  component: PageHeader,
  tags: ["autodocs"],
} satisfies Meta<typeof PageHeader>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    title: "Cases",
  },
}

export const WithDescription: Story = {
  args: {
    title: "Cases",
    description: "Manage your active investigations and archived cases.",
  },
}

export const WithActions: Story = {
  args: {
    title: "Cases",
    actions: <Button size="sm">New Case</Button>,
  },
}

export const WithBreadcrumbs: Story = {
  args: {
    title: "Operation Falcon",
    breadcrumbs: (
      <span>
        Cases <span className="mx-1">/</span> Operation Falcon
      </span>
    ),
  },
}

export const Full: Story = {
  args: {
    title: "Operation Falcon",
    description: "Cross-border financial fraud investigation.",
    breadcrumbs: (
      <span>
        Cases <span className="mx-1">/</span> Operation Falcon
      </span>
    ),
    actions: (
      <>
        <Button variant="outline" size="sm">
          Export
        </Button>
        <Button size="sm">Add Entity</Button>
      </>
    ),
  },
}
