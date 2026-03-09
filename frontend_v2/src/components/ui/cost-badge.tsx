import { cn } from "@/lib/cn"

interface CostBadgeProps {
  amount: number
  currency?: string
  className?: string
}

export function CostBadge({
  amount,
  currency = "USD",
  className,
}: CostBadgeProps) {
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(amount)

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md bg-amber-500/10 px-1.5 py-0.5 font-mono text-xs text-amber-500",
        className
      )}
    >
      {formatted}
    </span>
  )
}
