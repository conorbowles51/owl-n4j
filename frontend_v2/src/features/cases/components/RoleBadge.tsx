import { Badge } from "@/components/ui/badge"
import { Crown, Pencil, Eye, Shield } from "lucide-react"

const config: Record<string, { label: string; variant: "amber" | "info" | "slate" | "danger"; Icon: typeof Crown }> = {
  owner: { label: "Owner", variant: "amber", Icon: Crown },
  editor: { label: "Editor", variant: "info", Icon: Pencil },
  viewer: { label: "Viewer", variant: "slate", Icon: Eye },
  admin_access: { label: "Admin", variant: "danger", Icon: Shield },
}

interface RoleBadgeProps {
  role: string
  className?: string
}

export function RoleBadge({ role, className }: RoleBadgeProps) {
  const entry = config[role]
  if (!entry) return null
  const { label, variant, Icon } = entry
  return (
    <Badge variant={variant} className={className}>
      <Icon className="size-3" />
      {label}
    </Badge>
  )
}
