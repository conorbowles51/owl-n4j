import { X, Tag, ArrowRight, ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useFinancialStore } from "../stores/financial.store"

interface BulkActionsBarProps {
  onBulkCategorize: () => void
  onBulkSetFrom: () => void
  onBulkSetTo: () => void
}

export function BulkActionsBar({
  onBulkCategorize,
  onBulkSetFrom,
  onBulkSetTo,
}: BulkActionsBarProps) {
  const { checkedKeys, clearChecked } = useFinancialStore()

  if (checkedKeys.size === 0) return null

  return (
    <div className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/5 px-4 py-1.5">
      <Badge variant="amber" className="text-xs">
        {checkedKeys.size} selected
      </Badge>

      <Button variant="ghost" size="sm" onClick={onBulkCategorize}>
        <Tag className="size-3.5" />
        Categorize
      </Button>

      <Button variant="ghost" size="sm" onClick={onBulkSetFrom}>
        <ArrowLeft className="size-3.5" />
        Set From
      </Button>

      <Button variant="ghost" size="sm" onClick={onBulkSetTo}>
        <ArrowRight className="size-3.5" />
        Set To
      </Button>

      <div className="flex-1" />

      <Button variant="ghost" size="sm" onClick={clearChecked}>
        <X className="size-3.5" />
        Clear
      </Button>
    </div>
  )
}
