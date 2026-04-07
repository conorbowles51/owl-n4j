import { useCallback, useEffect, useState } from "react"
import { chatAPI } from "../api"
import type { ChatMessageData, ChatScope } from "../types"

interface QuickChatOptions {
  caseId: string | null
  model: string
  provider: string
  selectedKeys?: string[]
  scope: ChatScope
}

export function useQuickChat({
  caseId,
  model,
  provider,
  selectedKeys,
  scope,
}: QuickChatOptions) {
  const [messages, setMessages] = useState<ChatMessageData[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    setMessages([])
  }, [caseId])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!caseId) return

      const effectiveScope =
        scope === "selection" && (selectedKeys?.length ?? 0) > 0
          ? "selection"
          : "case_overview"

      const userMsg: ChatMessageData = {
        role: "user",
        content,
        scope: effectiveScope,
        selected_entity_keys:
          effectiveScope === "selection" ? selectedKeys : undefined,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])
      setIsLoading(true)

      try {
        const response = await chatAPI.ask({
          question: content,
          case_id: caseId,
          model,
          provider,
          scope: effectiveScope,
          selected_entity_keys:
            effectiveScope === "selection" ? selectedKeys : undefined,
          persist: false,
        })

        const assistantMsg: ChatMessageData = {
          id: response.message_id,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          cost: response.cost,
          timestamp: new Date().toISOString(),
          model_info: response.model_info,
          provenance: response.provenance,
        }
        setMessages((prev) => [...prev, assistantMsg])
      } catch (err) {
        const errorMsg: ChatMessageData = {
          role: "assistant",
          content:
            err instanceof Error
              ? `Error: ${err.message}`
              : "An error occurred. Please try again.",
          timestamp: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, errorMsg])
      } finally {
        setIsLoading(false)
      }
    },
    [caseId, model, provider, scope, selectedKeys]
  )

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  return { messages, isLoading, sendMessage, clearMessages }
}
