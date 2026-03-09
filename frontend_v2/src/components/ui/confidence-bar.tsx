import { cn } from "@/lib/cn"

interface ConfidenceBarProps {
  value: number // 0-1
  className?: string
  showLabel?: boolean
}

export function ConfidenceBar({
  value,
  className,
  showLabel = true,
}: ConfidenceBarProps) {
  const percentage = Math.round(value * 100)
  const color =
    percentage >= 75
      ? "bg-emerald-500"
      : percentage >= 50
        ? "bg-amber-500"
        : percentage >= 25
          ? "bg-yellow-500"
          : "bg-red-500"

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all duration-300", color)}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <span className="min-w-[2.5rem] text-right font-mono text-xs text-muted-foreground">
          {percentage}%
        </span>
      )}
    </div>
  )
}
