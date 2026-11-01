import type React from "react"
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
        "animate-spin text-primary",
        sizeClasses[size],
        className
      )}
    />
  )
}

/**
 * A wait that is not a data read (the sign-in check, a query the person ran, a screen's code arriving): the spinner
 * with the step in words, announced to screen readers. Data reads use the shared loading panel (LoadProgress).
 */
export function LoadingWords({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div aria-live="polite" className={cn("flex items-center gap-2 text-sm text-muted-foreground", className)}>
      <LoadingSpinner size="sm" />
      <span>{children}</span>
    </div>
  )
}
