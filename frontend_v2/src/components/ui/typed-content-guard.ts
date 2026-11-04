import * as React from "react"

export const DISCARD_TYPED_PROMPT =
  "You have typed in this window. Close it and lose what you typed?"

const TEXT_INPUT_TYPES = new Set([
  "", "text", "email", "url", "tel", "number", "password", "date", "datetime-local", "time", "month", "week",
])

/**
 * True when an input event came from a field that holds a person's work: a textarea, a text input or an editable
 * block. Checkboxes, radios and ranges are not typed work, and neither is a search or filter box (type=search, a
 * combobox, a placeholder starting "Search", or data-typed-guard="off"): losing a search query loses nothing.
 */
export function isTypedField(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== "string") return false
  const el = target as HTMLElement
  if (el.closest?.('[data-typed-guard="off"]')) return false
  if (el.getAttribute("role") === "combobox") return false
  if (/^\s*search\b/i.test(el.getAttribute("placeholder") ?? "")) return false
  if (el.tagName === "TEXTAREA") return true
  if (el.tagName === "INPUT") return TEXT_INPUT_TYPES.has(((el as HTMLInputElement).type || "").toLowerCase())
  return el.isContentEditable === true
}

type DismissEvent = { preventDefault: () => void; defaultPrevented?: boolean }

interface GuardHandlers<P, E> {
  onInputCapture?: React.InputEventHandler<HTMLDivElement>
  onPointerDownOutside?: (event: P) => void
  onInteractOutside?: (event: E) => void
  onEscapeKeyDown?: (event: KeyboardEvent) => void
}

/**
 * A dialog or sheet the person has typed into does not close on an outside click or Escape without asking.
 * The close button, Cancel and Save stay explicit and unprompted. The flag lives in the mounted content, so it
 * starts clean every time the window opens.
 */
export function useTypedContentGuard<P extends DismissEvent, E extends DismissEvent>(
  enabled: boolean,
  handlers: GuardHandlers<P, E>,
  confirm: (message: string) => boolean = (m) => window.confirm(m),
) {
  const typed = React.useRef(false)
  const { onInputCapture, onPointerDownOutside, onInteractOutside, onEscapeKeyDown } = handlers

  const guard = React.useCallback(
    (event: DismissEvent) => {
      if (!enabled || event.defaultPrevented || !typed.current) return
      if (!confirm(DISCARD_TYPED_PROMPT)) event.preventDefault()
    },
    [enabled, confirm],
  )

  return {
    onInputCapture: (event: React.InputEvent<HTMLDivElement>) => {
      if (isTypedField(event.target)) typed.current = true
      onInputCapture?.(event)
    },
    onPointerDownOutside: (event: P) => {
      onPointerDownOutside?.(event)
      guard(event)
    },
    // Focus moving outside (e.g. a click into another portal) is the second way Radix dismisses; it never prompts,
    // it only holds the window open while something is typed (the pointer handler above already asked).
    onInteractOutside: (event: E) => {
      onInteractOutside?.(event)
      if (enabled && typed.current && !event.defaultPrevented && (event as unknown as { type?: string }).type === "dismissableLayer.focusOutside") {
        event.preventDefault()
      }
    },
    onEscapeKeyDown: (event: KeyboardEvent) => {
      onEscapeKeyDown?.(event)
      guard(event)
    },
  }
}
