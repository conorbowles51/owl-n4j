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
        "min-h-[4rem] w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 caret-primary shadow-xs transition-[border-color,box-shadow] outline-none",
        "placeholder:text-muted-foreground",
        "focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/30",
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
