"use client"

import * as React from "react"
import { Tooltip as TooltipPrimitive } from "radix-ui"

import { cn } from "@/lib/cn"

/** Set under a TooltipProvider, so a Tooltip outside one (a test, a portal) brings its own instead of failing. */
const InProvider = React.createContext(false)

function TooltipProvider({
  delayDuration = 0,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return (
    <InProvider.Provider value={true}>
      <TooltipPrimitive.Provider
        data-slot="tooltip-provider"
        delayDuration={delayDuration}
        {...props}
      />
    </InProvider.Provider>
  )
}

/**
 * Whether the last thing the person did was press a pointer rather than a key. A dialog opened by a click moves
 * focus to its first control; a tooltip opened by that focus would take the first Escape away from the dialog.
 * Focus opens a tooltip only when it came from the keyboard (or from code before any pointer press).
 */
let pointerLast = false
if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", () => void (pointerLast = true), { capture: true })
  document.addEventListener("mousedown", () => void (pointerLast = true), { capture: true })
  document.addEventListener("keydown", () => void (pointerLast = false), { capture: true })
}

/** When keyboard focus last reached this tooltip's control, and which control. */
type Mark = { at: number; el: Element | null; scrolled: boolean }
const FocusMark = React.createContext<React.RefObject<Mark> | null>(null)

function Tooltip({
  open: openProp,
  defaultOpen,
  onOpenChange,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  const [own, setOwn] = React.useState(defaultOpen ?? false)
  const focusRef = React.useRef<Mark>({ at: -Infinity, el: null, scrolled: false })
  const change = (next: boolean) => {
    // Focus can scroll a narrow panel to bring its control into view, and the tooltip closes on any scroll around
    // its control: keep it open while that control still has focus, just after focus opened it.
    const mark = focusRef.current
    if (!next && mark.scrolled && document.activeElement === mark.el && performance.now() - mark.at < 400) return
    setOwn(next)
    onOpenChange?.(next)
  }
  const root = <TooltipPrimitive.Root data-slot="tooltip" open={openProp ?? own} onOpenChange={change} {...props} />
  const marked = <FocusMark.Provider value={focusRef}>{root}</FocusMark.Provider>
  return React.useContext(InProvider) ? marked : <TooltipProvider>{marked}</TooltipProvider>
}

function TooltipTrigger({
  onFocus,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  const focusRef = React.useContext(FocusMark)
  return (
    <TooltipPrimitive.Trigger
      data-slot="tooltip-trigger"
      onFocus={(event) => {
        if (focusRef) {
          const mark: Mark = { at: performance.now(), el: event.currentTarget, scrolled: false }
          focusRef.current = mark
          // registered before the open tooltip's own scroll watch, so it is marked before that closes it
          const scrolled = () => void (mark.scrolled = true)
          window.addEventListener("scroll", scrolled, { capture: true })
          setTimeout(() => window.removeEventListener("scroll", scrolled, { capture: true }), 400)
        }
        onFocus?.(event)
        // the primitive skips its own open when the event is marked handled
        if (pointerLast) event.preventDefault()
      }}
      {...props}
    />
  )
}

function TooltipContent({
  className,
  sideOffset = 0,
  children,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 w-fit max-w-[min(24rem,calc(100vw-1rem))] origin-(--radix-tooltip-content-transform-origin) animate-in rounded-md bg-slate-950 px-3 py-1.5 text-xs text-balance text-white shadow-lg fade-in-0 zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
          className
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="z-50 size-2.5 translate-y-[calc(-50%_-_2px)] rotate-45 rounded-[2px] bg-slate-950 fill-slate-950" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  )
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
