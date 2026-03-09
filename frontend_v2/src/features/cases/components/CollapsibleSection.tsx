import { ChevronDown, ChevronRight, type LucideIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"

interface CollapsibleSectionProps {
  title: string
  icon: LucideIcon
  count?: number
  isExpanded: boolean
  onToggle: () => void
  children: React.ReactNode
  className?: string
}

export function CollapsibleSection({
  title,
  icon: Icon,
  count,
  isExpanded,
  onToggle,
  children,
  className,
}: CollapsibleSectionProps) {
  return (
    <div className={cn("border-b border-border", className)}>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-accent/50"
      >
        {isExpanded ? (
          <ChevronDown className="size-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3.5 text-muted-foreground" />
        )}
        <Icon className="size-3.5 text-amber-500" />
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </span>
        {count !== undefined && (
          <Badge variant="slate" className="ml-auto text-[10px]">
            {count}
          </Badge>
        )}
      </button>
      {isExpanded && <div className="px-4 pb-3">{children}</div>}
    </div>
  )
}
