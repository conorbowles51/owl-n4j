import { useEffect, useRef, useState } from "react"
import { HelpCircle, Search, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { compactNumber } from "../shared/cellebrite-format"

export function TimelineSearchInput({
  value,
  onChange,
  matchCount,
  totalCount,
}: {
  value: string
  onChange: (value: string) => void
  matchCount: number
  totalCount: number
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const hintTimeoutRef = useRef<number | null>(null)
  const [hintOpen, setHintOpen] = useState(false)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && value) {
        onChange("")
        return
      }
      if (event.key !== "/") return
      const target = document.activeElement
      const tag = target?.tagName.toLowerCase()
      if (tag === "input" || tag === "textarea" || (target instanceof HTMLElement && target.isContentEditable)) return
      event.preventDefault()
      inputRef.current?.focus()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [onChange, value])

  useEffect(
    () => () => {
      if (hintTimeoutRef.current !== null) window.clearTimeout(hintTimeoutRef.current)
    },
    []
  )

  function updateValue(nextValue: string) {
    onChange(nextValue)
    if (!nextValue.includes(":") || value.includes(":")) return
    setHintOpen(true)
    if (hintTimeoutRef.current !== null) window.clearTimeout(hintTimeoutRef.current)
    hintTimeoutRef.current = window.setTimeout(() => setHintOpen(false), 3500)
  }

  return (
    <div className="relative flex items-center gap-2">
      <div className="relative min-w-0 flex-1">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={inputRef}
          value={value}
          onChange={(event) => updateValue(event.target.value)}
          placeholder='Search events - try type:call from:John app:WhatsApp before:2023-01-15'
          className="h-9 pl-8 pr-20 text-sm"
        />
        <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">
          {compactNumber(matchCount)} / {compactNumber(totalCount)}
        </span>
      </div>
      {value ? (
        <Button type="button" variant="ghost" size="icon-sm" onClick={() => onChange("")} title="Clear timeline search">
          <X className="size-4" />
        </Button>
      ) : null}
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={() => setHintOpen((current) => !current)}
        title="Search operators"
      >
        <HelpCircle className="size-4" />
      </Button>
      {hintOpen ? (
        <div className="absolute right-0 top-10 z-30 w-80 rounded-md border border-border bg-popover p-3 text-xs text-popover-foreground shadow-lg">
          <div className="font-semibold">Timeline search</div>
          <div className="mt-2 grid grid-cols-[72px_1fr] gap-x-3 gap-y-1 text-muted-foreground">
            <span className="font-mono text-foreground">type:</span>
            <span>call, message, location, wifi, app session</span>
            <span className="font-mono text-foreground">from:/to:</span>
            <span>sender, recipient, counterpart</span>
            <span className="font-mono text-foreground">app:</span>
            <span>source app, for example WhatsApp</span>
            <span className="font-mono text-foreground">phone:</span>
            <span>device label, owner, model, P1/P2</span>
            <span className="font-mono text-foreground">before:</span>
            <span>or after: with ISO dates</span>
            <span className="font-mono text-foreground">-term</span>
            <span>exclude a word or quoted phrase</span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
