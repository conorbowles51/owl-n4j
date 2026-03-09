import { Badge } from "@/components/ui/badge"

const statusConfig = {
  processed: { variant: "success" as const, label: "Processed" },
  processing: { variant: "amber" as const, label: "Processing" },
  queued: { variant: "slate" as const, label: "Queued" },
  failed: { variant: "danger" as const, label: "Failed" },
  unprocessed: { variant: "slate" as const, label: "Unprocessed" },
} as const

export type ProcessingStatus = keyof typeof statusConfig

export function StatusIndicator({
  status,
}: {
  status: ProcessingStatus
}) {
  const config = statusConfig[status]
  return <Badge variant={config.variant}>{config.label}</Badge>
}
