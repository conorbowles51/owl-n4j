import { cn } from "@/lib/cn"
import { Loader2 } from "lucide-react"

interface LoadingSpinnerProps {
  size?: "sm" | "default" | "lg"
  className?: string
}

const sizeClasses = {
  sm: "size-4",
  default: "size-6",
  lg: "size-8",
}

export function LoadingSpinner({
  size = "default",
  className,
}: LoadingSpinnerProps) {
  return (
    <Loader2
      className={cn(
        "animate-spin text-amber-500",
        sizeClasses[size],
        className
      )}
    />
  )
}
