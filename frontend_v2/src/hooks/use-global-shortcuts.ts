import { useMemo } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useKeyboardShortcuts } from "./use-keyboard-shortcuts"

export function useGlobalShortcuts(caseIdOverride?: string | null) {
  const navigate = useNavigate()
  const { id: paramsCaseId } = useParams()
  const caseId = caseIdOverride ?? paramsCaseId

  const shortcuts = useMemo(() => {
    const base: {
      key: string
      meta?: boolean
      ctrl?: boolean
      shift?: boolean
      handler: () => void
    }[] = [
      {
        key: "k",
        meta: true,
        handler: () => {
          document.dispatchEvent(new CustomEvent("owl:toggle-command-palette"))
        },
      },
      {
        key: "Escape",
        handler: () => {
          document.dispatchEvent(new CustomEvent("owl:escape"))
        },
      },
    ]

    if (caseId) {
      const views = [
        "graph",
        "timeline",
        "map",
        "table",
        "financial",
        "cellebrite",
        "profiles",
        "evidence",
      ]

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

  useKeyboardShortcuts(shortcuts)
}
