import type { Meta } from "@storybook/react-vite"
import { StatusIndicator } from "@/components/ui/status-indicator"
import type { ProcessingStatus } from "@/components/ui/status-indicator"

const meta = {
  title: "@owl/ui/StatusIndicator",
  component: StatusIndicator,
  tags: ["autodocs"],
} satisfies Meta<typeof StatusIndicator>

export default meta

const allStatuses: ProcessingStatus[] = [
  "processed",
  "processing",
  "queued",
  "failed",
  "unprocessed",
]

export const AllStatuses = {
  render: () => (
    <div className="flex gap-2">
      {allStatuses.map((status) => (
        <StatusIndicator key={status} status={status} />
      ))}
    </div>
  ),
}
