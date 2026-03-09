import * as React from "react"
import { cn } from "@/lib/cn"

interface CypherInputProps
  extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "onExecute"> {
  onExecute?: (value: string) => void
}

export const CypherInput = React.forwardRef<
  HTMLTextAreaElement,
  CypherInputProps
>(({ className, onExecute, onKeyDown, ...props }, ref) => {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      onExecute?.(e.currentTarget.value)
    }
    onKeyDown?.(e)
  }

  return (
    <textarea
      ref={ref}
      className={cn(
        "min-h-[4rem] w-full rounded-md border border-input bg-slate-950 px-3 py-2 font-mono text-sm text-foreground shadow-xs transition-[color,box-shadow] outline-none",
        "placeholder:text-muted-foreground",
        "focus-visible:border-amber-500 focus-visible:ring-2 focus-visible:ring-amber-500/40",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      onKeyDown={handleKeyDown}
      spellCheck={false}
      {...props}
    />
  )
})

CypherInput.displayName = "CypherInput"
