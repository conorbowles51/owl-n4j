import {
  Building2,
  CalendarDays,
  Car,
  CircleDot,
  MapPin,
  Smartphone,
  UserRound,
} from "lucide-react"
import { cn } from "@/lib/cn"

const kinds = {
  person: {
    icon: UserRound,
    label: "Person",
    color: "text-blue-600 dark:text-blue-400 bg-blue-500/10",
  },
  organisation: {
    icon: Building2,
    label: "Organisation",
    color: "text-violet-600 dark:text-violet-400 bg-violet-500/10",
  },
  device: {
    icon: Smartphone,
    label: "Device",
    color: "text-cyan-700 dark:text-cyan-400 bg-cyan-500/10",
  },
  vehicle: {
    icon: Car,
    label: "Vehicle",
    color: "text-orange-700 dark:text-orange-400 bg-orange-500/10",
  },
  address: {
    icon: MapPin,
    label: "Address",
    color: "text-emerald-700 dark:text-emerald-400 bg-emerald-500/10",
  },
  event: {
    icon: CalendarDays,
    label: "Event",
    color: "text-amber-700 dark:text-amber-400 bg-amber-500/10",
  },
  other: {
    icon: CircleDot,
    label: "Subject",
    color: "text-muted-foreground bg-muted",
  },
}

export function DossierIcon({
  type,
  className,
}: {
  type: string
  className?: string
}) {
  const { icon: Icon, color } = Object.hasOwn(kinds, type)
    ? kinds[type as keyof typeof kinds]
    : kinds.other
  return (
    <span
      className={cn(
        "grid size-10 shrink-0 place-items-center rounded-xl",
        color,
        className
      )}
    >
      <Icon className="size-[18px]" aria-hidden="true" />
    </span>
  )
}
