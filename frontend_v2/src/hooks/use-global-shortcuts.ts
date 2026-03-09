import { useCallback } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useKeyboardShortcuts } from "./use-keyboard-shortcuts"

export function useGlobalShortcuts() {
  const navigate = useNavigate()
  const { id: caseId } = useParams()

  const shortcuts = useCallback(() => {
    const base: { key: string; meta?: boolean; ctrl?: boolean; shift?: boolean; handler: () => void }[] = [
      // Cmd+K → command palette (dispatches custom event)
      {
        key: "k",
        meta: true,
        handler: () => {
          document.dispatchEvent(new CustomEvent("owl:toggle-command-palette"))
        },
      },
      // Escape → close topmost modal/panel
      {
        key: "Escape",
        handler: () => {
          document.dispatchEvent(new CustomEvent("owl:escape"))
        },
      },
    ]

    // View shortcuts only when in a case
    if (caseId) {
      const views = ["graph", "timeline", "map", "table", "financial"]
      views.forEach((view, i) => {
        base.push({
          key: String(i + 1),
          meta: true,
          handler: () => navigate(`/cases/${caseId}/${view}`),
        })
      })
    }

    return base
  }, [caseId, navigate])

  useKeyboardShortcuts(shortcuts())
}
