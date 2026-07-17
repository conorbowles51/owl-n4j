import { useEffect } from "react"

interface ShortcutHandler {
  key: string
  code?: string
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
  handler: () => void
}

export function useKeyboardShortcuts(shortcuts: ShortcutHandler[]) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      for (const shortcut of shortcuts) {
        const metaOrCtrl = shortcut.meta || shortcut.ctrl
        const metaMatch = metaOrCtrl
          ? e.metaKey || e.ctrlKey
          : !e.metaKey && !e.ctrlKey
        const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey
        const keyMatch = shortcut.code
          ? e.code === shortcut.code
          : e.key.toLowerCase() === shortcut.key.toLowerCase()

        if (
          keyMatch &&
          metaMatch &&
          shiftMatch
        ) {
          e.preventDefault()
          shortcut.handler()
          return
        }
      }
    }

    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [shortcuts])
}
