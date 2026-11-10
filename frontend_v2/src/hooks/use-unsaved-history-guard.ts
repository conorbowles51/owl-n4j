import { useEffect } from "react"

interface NavigationEvent extends Event {
  navigationType: string
  destination?: { sameDocument?: boolean }
}
type BrowserNavigation = EventTarget

const guards = new Map<symbol, string>()
let release: (() => void) | undefined
let remember: (() => void) | undefined
let forget: (() => void) | undefined

/** Call before an app-owned tab or link action that would unmount active drafts. */
export function confirmUnsavedNavigation() {
  const messages = [...guards.values()]
  return (
    !messages.length ||
    window.confirm(
      messages.length > 1
        ? "Discard your unsaved changes and leave this page?"
        : messages[0]
    )
  )
}

function install() {
  let savedState: { idx?: number } | null = null
  let savedUrl = ""
  let restoring = false
  const navigation = (window as Window & { navigation?: BrowserNavigation })
    .navigation
  remember = () => {
    if (restoring || !guards.size) return
    savedState = window.history.state
    savedUrl = window.location.href
  }
  forget = () => { savedState = null; savedUrl = ""; approvedTraversal = false }
  const onNavigate = (event: Event) => {
    const change = event as NavigationEvent
    // Never cancel pushState/replaceState: BrowserRouter has already decided to navigate.
    // Some browser traversals cannot be cancelled; those use the popstate fallback below.
    if (
      !(window as Window & { navigation?: BrowserNavigation }).navigation ||
      !guards.size ||
      restoring ||
      change.navigationType !== "traverse" ||
      !change.cancelable ||
      !change.destination?.sameDocument
    )
      return
    if (!confirmUnsavedNavigation()) change.preventDefault()
    else approvedTraversal = true
  }
  let approvedTraversal = false
  const onPop = (event: PopStateEvent) => {
    if (restoring) {
      event.stopImmediatePropagation()
      restoring = false
      approvedTraversal = false
      return
    }
    if (!guards.size) return
    if (approvedTraversal || confirmUnsavedNavigation()) {
      approvedTraversal = false
      remember?.()
      return
    }
    // popstate itself is not cancelable. Keep it away from BrowserRouter so its
    // React tree (and all drafts) stays mounted while we restore the history entry.
    event.stopImmediatePropagation()
    const previousIndex = savedState?.idx
    const nextIndex = event.state?.idx
    if (
      typeof previousIndex === "number" &&
      typeof nextIndex === "number" &&
      previousIndex !== nextIndex
    ) {
      restoring = true
      window.history.go(previousIndex - nextIndex)
    } else {
      // A same-document hash entry or another script may not have Router's idx.
      // Restore the known URL/state without guessing a traversal direction.
      window.history.pushState(savedState, "", savedUrl)
    }
  }
  const onUnload = (event: BeforeUnloadEvent) => {
    if (!guards.size) return
    event.preventDefault()
    event.returnValue = ""
  }
  navigation?.addEventListener("navigate", onNavigate)
  // Installed at app startup, before BrowserRouter. At the Window target listener
  // registration order matters even with capture; a late listener cannot save drafts.
  window.addEventListener("popstate", onPop, true)
  window.addEventListener("beforeunload", onUnload)
  return () => {
    navigation?.removeEventListener("navigate", onNavigate)
    window.removeEventListener("popstate", onPop, true)
    window.removeEventListener("beforeunload", onUnload)
    remember = undefined
  }
}

/** Run once at app startup, before mounting BrowserRouter. Dormant when no drafts are dirty. */
export function initializeUnsavedHistoryGuard() {
  if (typeof window !== "undefined" && !release) release = install()
}

/** Protect browser Back/Forward and page unloads. Keep explicit guards on app tab/link actions. */
export function useUnsavedHistoryGuard(
  dirty: boolean,
  message = "Discard your unsaved changes and leave this page?"
) {
  useEffect(() => {
    if (!dirty) return
    const key = Symbol("unsaved draft")
    guards.set(key, message)
    initializeUnsavedHistoryGuard()
    return () => {
      guards.delete(key)
      if (!guards.size) forget?.()
    }
  }, [dirty, message])
  // A deliberate in-app navigation can keep the form mounted. Track its new
  // history entry after rendering, without rerunning registration on every keystroke.
  useEffect(() => {
    if (dirty) remember?.()
  })
}
