import { BrainCircuit, SlidersHorizontal } from "lucide-react"
import { Link, useLocation } from "react-router-dom"
import { cn } from "@/lib/cn"

const items = [
  { to: "/settings", label: "General", icon: SlidersHorizontal, end: true },
  { to: "/settings/ai", label: "AI settings", icon: BrainCircuit, end: false },
]

export function SettingsNav() {
  const { pathname } = useLocation()

  return (
    <nav aria-label="Settings sections" className="flex gap-1 rounded-lg border border-border/70 bg-muted/35 p-1">
      {items.map((item) => {
        const active = item.end ? pathname === item.to : pathname.startsWith(item.to)
        const Icon = item.icon
        return (
          <Link
            key={item.to}
            to={item.to}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-xs font-medium transition-colors",
              active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-background/60 hover:text-foreground"
            )}
          >
            <Icon className="size-3.5" />
            {item.label}
          </Link>
        )
      })}
    </nav>
  )
}
