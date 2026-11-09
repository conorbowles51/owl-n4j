import { useEffect, useState } from "react"

import { agentAPI } from "./api"
import type { AgentModelChoice } from "./types"

/** The models the agent may use, the Settings default first (GET /api/agent/models). Empty until loaded. */
export function useAgentModelChoices(): AgentModelChoice[] {
  const [choices, setChoices] = useState<AgentModelChoice[]>([])
  useEffect(() => {
    let cancelled = false
    agentAPI
      .listModels()
      .then((payload) => {
        if (!cancelled) setChoices(payload.choices ?? [])
      })
      .catch(() => {
        if (!cancelled) setChoices([])
      })
    return () => {
      cancelled = true
    }
  }, [])
  return choices
}

/** What a send carries for a picked choice: nothing for the default, so the Settings default applies. */
export function modelParams(choice: AgentModelChoice | undefined): { model?: string; reasoning?: AgentModelChoice["reasoning"] } {
  if (!choice || choice.default) return {}
  return { model: choice.model_id, reasoning: choice.reasoning }
}
