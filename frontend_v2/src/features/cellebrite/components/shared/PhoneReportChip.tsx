import { Smartphone } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"
import type { PhoneReport } from "../../types"
import { reportTitle } from "./cellebrite-format"

export function PhoneReportChip({
  reportKey,
  reports,
  className,
}: {
  reportKey: string
  reports: PhoneReport[]
  className?: string
}) {
  const report = reports.find((item) => item.report_key === reportKey)
  return (
    <Badge variant="outline" className={cn("max-w-48 gap-1 rounded-md font-mono text-[10px]", className)}>
      <Smartphone className="size-3 text-emerald-600" />
      <span className="truncate">{report ? reportTitle(report) : reportKey}</span>
    </Badge>
  )
}
