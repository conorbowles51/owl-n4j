import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"
import type { LucideIcon } from "lucide-react"

interface WorkspaceSectionProps {
  title: string
  icon: LucideIcon
  count?: number
  defaultOpen?: boolean
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export function WorkspaceSection({
  title,
  icon: Icon,
  count,
  defaultOpen = true,
  actions,
  children,
  className,
}: WorkspaceSectionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={cn("border-b border-border", className)}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-muted/30"
      >
        {open ? (
          <ChevronDown className="size-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3.5 text-muted-foreground" />
        )}
        <Icon className="size-3.5 text-amber-500" />
        <span className="flex-1 text-xs font-semibold">{title}</span>
        {count !== undefined && (
          <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
            {count}
          </Badge>
        )}
        {actions && (
          <div
            className="flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            {actions}
          </div>
        )}
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  )
}
