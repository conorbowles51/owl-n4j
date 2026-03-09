import { cn } from "@/lib/cn"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"

interface User {
  name: string
  initials?: string
}

interface PresenceIndicatorProps {
  users: User[]
  maxVisible?: number
  className?: string
}

export function PresenceIndicator({
  users,
  maxVisible = 3,
  className,
}: PresenceIndicatorProps) {
  const visible = users.slice(0, maxVisible)
  const overflow = users.length - maxVisible

  return (
    <div className={cn("flex -space-x-2", className)}>
      {visible.map((user, i) => (
        <Avatar key={i} className="size-6 border-2 border-background">
          <AvatarFallback className="bg-slate-700 text-[10px] text-slate-200">
            {user.initials ?? user.name.slice(0, 2).toUpperCase()}
          </AvatarFallback>
        </Avatar>
      ))}
      {overflow > 0 && (
        <Avatar className="size-6 border-2 border-background">
          <AvatarFallback className="bg-slate-600 text-[10px] text-slate-200">
            +{overflow}
          </AvatarFallback>
        </Avatar>
      )}
    </div>
  )
}
