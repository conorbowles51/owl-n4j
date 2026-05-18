import { Smartphone } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"
import type { PhoneReport } from "../../types"
import { reportTitle } from "./cellebrite-format"

export function PhoneReportChip({
  reportKey,
  report,
  reports,
  color,
  compact = false,
  className,
}: {
  reportKey: string
  report?: PhoneReport
  reports?: PhoneReport[]
  color?: string
  compact?: boolean
  className?: string
}) {
  const resolvedReport = report ?? reports?.find((item) => item.report_key === reportKey)
  return (
    <Badge
      variant="outline"
      className={cn(
        "max-w-48 gap-1 rounded-md font-mono text-[10px]",
        compact && "max-w-32 px-1.5 py-0",
        className
      )}
    >
      {color ? (
        <span className="size-2.5 shrink-0 rounded-sm" style={{ backgroundColor: color }} />
      ) : (
        <Smartphone className="size-3 text-emerald-600" />
      )}
      <span className="truncate">{resolvedReport ? reportTitle(resolvedReport) : reportKey}</span>
    </Badge>
  )
}
