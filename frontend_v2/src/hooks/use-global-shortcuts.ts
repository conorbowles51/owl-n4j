import { useMemo } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { CASE_VIEW_SHORTCUTS } from "@/lib/shortcuts-registry"
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
      code?: string
      handler: () => void
    }[] = []

    if (caseId) {
      CASE_VIEW_SHORTCUTS.forEach((shortcut) => {
        base.push({
          key: shortcut.key,
          code: shortcut.code,
          meta: true,
          shift: true,
          handler: () => navigate(`/cases/${caseId}/${shortcut.view}`),
        })
      })
    }

    return base
  }, [caseId, navigate])

  useKeyboardShortcuts(shortcuts)
}
