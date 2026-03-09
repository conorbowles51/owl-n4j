import { cn } from "@/lib/cn"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Crown, Pencil, Eye, Shield } from "lucide-react"

interface CaseCardProps {
  title: string
  description?: string | null
  userRole?: "owner" | "editor" | "viewer" | "admin_access"
  ownerName?: string | null
  lastUpdated?: string
  className?: string
  onClick?: () => void
}

const roleConfig = {
  owner: { label: "Owner", variant: "amber" as const, icon: Crown },
  editor: { label: "Editor", variant: "info" as const, icon: Pencil },
  viewer: { label: "Viewer", variant: "slate" as const, icon: Eye },
  admin_access: { label: "Admin", variant: "danger" as const, icon: Shield },
}

export function CaseCard({
  title,
  description,
  userRole,
  ownerName,
  lastUpdated,
  className,
  onClick,
}: CaseCardProps) {
  const role = userRole ? roleConfig[userRole] : null
  const RoleIcon = role?.icon

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
          <CardTitle className="truncate">{title}</CardTitle>
          {role && (
            <Badge variant={role.variant}>
              {RoleIcon && <RoleIcon className="size-3" />}
              {role.label}
            </Badge>
          )}
        </div>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      {(ownerName || lastUpdated) && (
        <div className="flex items-center gap-3 px-4 pb-3 text-xs text-muted-foreground">
          {ownerName && <span>Owner: {ownerName}</span>}
          {lastUpdated && (
            <span>{new Date(lastUpdated).toLocaleDateString()}</span>
          )}
        </div>
      )}
    </Card>
  )
}
