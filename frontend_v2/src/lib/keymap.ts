/**
 * The one keymap registry (07 4.9). Screens register bindings while mounted; one global listener dispatches them.
 * One key has one meaning across every screen and queue: registering a key with a different meaning throws, so a
 * conflict fails a test instead of reaching a person. Every key has a visible control; the `?` overlay is
 * generated from what is registered now. Keys are ignored while typing in a field, except Esc.
 */

export interface KeyMeaning {
  key: string
  meaning: string
}

/** The fixed meanings (07 4.9 table). A screen may leave a key unbound, never rebind it. */
export const KEY_MEANINGS: Record<string, string> = {
  j: "Move down",
  k: "Move up",
  ArrowDown: "Move down",
  ArrowUp: "Move up",
  "Shift+J": "Extend selection down",
  "Shift+K": "Extend selection up",
  "Shift+ArrowDown": "Extend selection down",
  "Shift+ArrowUp": "Extend selection up",
  Enter: "Open",
  r: "Record panel",
  a: "Around this time",
  c: "Add to…",
  "c d": "Add to a dossier",
  "c w": "Add to a finding or theory",
  "c n": "Add to a note",
  "c t": "Add to the Timeline",
  "c l": "Apply a label",
  "/": "Search within the filters",
  "Mod+F": "Find in these results",
  g: "Go to date",
  "Alt+J": "Next day",
  "Alt+K": "Previous day",
  o: "Original time value",
  p: "Names: this phone or the case",
  m: "Mark reviewed",
  y: "Yes",
  x: "No",
  s: "Skip",
  " ": "Select",
  "Mod+A": "Select the whole result",
  Escape: "Close or return",
  "?": "Show keys",
}

export interface Binding {
  key: string
  /** Visible label naming the outcome on this screen, e.g. "Looks right" for y. */
  label: string
  run: (event: KeyboardEvent) => void
  /** Hidden from the overlay only when its control is the overlay itself. */
  hidden?: boolean
}

interface Registration {
  scope: string
  bindings: Binding[]
}

const registrations = new Map<number, Registration>()
const listeners = new Set<() => void>()
let nextId = 1
let pending: { prefix: string; at: number } | null = null
const SEQUENCE_MS = 1500

function notify() {
  for (const l of listeners) l()
}

export function subscribeKeymap(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function register(scope: string, bindings: Binding[]): () => void {
  for (const b of bindings) {
    const meaning = KEY_MEANINGS[b.key]
    if (!meaning) throw new Error(`Key "${b.key}" has no meaning in the keymap (07 4.9); add it there first`)
  }
  const id = nextId++
  registrations.set(id, { scope, bindings })
  notify()
  return () => {
    registrations.delete(id)
    notify()
  }
}

/** What the `?` overlay lists: the bindings active now, newest screen first, one row per key. */
export function activeBindings(): { scope: string; key: string; label: string; meaning: string }[] {
  const seen = new Set<string>()
  const out: { scope: string; key: string; label: string; meaning: string }[] = []
  for (const reg of [...registrations.values()].reverse()) {
    for (const b of reg.bindings) {
      if (b.hidden || seen.has(b.key)) continue
      seen.add(b.key)
      out.push({ scope: reg.scope, key: b.key, label: b.label, meaning: KEY_MEANINGS[b.key] })
    }
  }
  return out
}

export function keyName(event: KeyboardEvent): string {
  let base = event.key
  const letter = (k: string) => k.length === 1 && /[a-z]/i.test(k)
  // Alt changes event.key on some layouts (Option+J on a Mac gives a symbol): use the physical key there.
  if (event.altKey && event.code?.startsWith("Key")) base = event.code.slice(3)
  const parts: string[] = []
  if (event.metaKey || event.ctrlKey) parts.push("Mod")
  if (event.altKey) parts.push("Alt")
  if (event.shiftKey && (letter(base) || base.length > 1)) parts.push("Shift")
  if (letter(base)) base = parts.length ? base.toUpperCase() : base.toLowerCase()
  parts.push(base)
  return parts.join("+")
}

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el || !el.tagName) return false
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)
}

function find(key: string): Binding | undefined {
  for (const reg of [...registrations.values()].reverse()) {
    const b = reg.bindings.find((x) => x.key === key)
    if (b) return b
  }
  return undefined
}

/** The global listener. Returns true when a binding ran (the event is then prevented). */
export function dispatchKey(event: KeyboardEvent, now = Date.now()): boolean {
  const name = keyName(event)
  if (typing(event.target) && name !== "Escape") return false
  if (pending && now - pending.at <= SEQUENCE_MS) {
    const seq = find(`${pending.prefix} ${name}`)
    pending = null
    if (seq) {
      event.preventDefault()
      seq.run(event)
      return true
    }
  }
  pending = null
  const binding = find(name)
  const startsSequence = [...registrations.values()].some((r) => r.bindings.some((b) => b.key.startsWith(`${name} `)))
  if (startsSequence) pending = { prefix: name, at: now }
  if (!binding) return startsSequence
  event.preventDefault()
  binding.run(event)
  return true
}

let installed = false
export function installKeymap(target: Window = window) {
  if (installed) return
  installed = true
  target.addEventListener("keydown", (e) => {
    if (!e.defaultPrevented) dispatchKey(e)
  })
}

export function resetKeymapForTest() {
  registrations.clear()
  pending = null
  notify()
}
