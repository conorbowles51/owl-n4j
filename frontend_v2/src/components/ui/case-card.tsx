import { cn } from "@/lib/cn"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

interface CaseCardProps {
  name: string
  description?: string
  status: "active" | "archived" | "closed"
  memberCount?: number
  lastUpdated?: string
  className?: string
  onClick?: () => void
}

const statusVariant = {
  active: "success",
  archived: "slate",
  closed: "amber",
} as const

export function CaseCard({
  name,
  description,
  status,
  memberCount,
  lastUpdated,
  className,
  onClick,
}: CaseCardProps) {
  return (
    <Card
      className={cn(
        "transition-colors duration-200 hover:border-slate-300 dark:hover:border-slate-600",
        onClick && "cursor-pointer",
        className
      )}
      onClick={onClick}
    >
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="truncate">{name}</CardTitle>
          <Badge variant={statusVariant[status]}>{status}</Badge>
        </div>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      {(memberCount !== undefined || lastUpdated) && (
        <div className="flex items-center gap-3 px-4 text-xs text-muted-foreground">
          {memberCount !== undefined && (
            <span>
              {memberCount} member{memberCount !== 1 ? "s" : ""}
            </span>
          )}
          {lastUpdated && <span>{lastUpdated}</span>}
        </div>
      )}
    </Card>
  )
}
