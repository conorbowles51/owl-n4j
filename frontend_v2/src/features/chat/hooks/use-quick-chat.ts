import { useState, useCallback } from "react"
import { chatAPI } from "../api"
import type { ChatMessageData } from "../types"

interface QuickChatOptions {
  caseId: string | null
  model: string
  provider: string
  selectedKeys?: string[]
}

export function useQuickChat({ caseId, model, provider, selectedKeys }: QuickChatOptions) {
  const [messages, setMessages] = useState<ChatMessageData[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const sendMessage = useCallback(
    async (content: string) => {
      if (!caseId) return

      const userMsg: ChatMessageData = {
        role: "user",
        content,
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
          ...(selectedKeys && selectedKeys.length > 0 && { selected_keys: selectedKeys }),
        })

        const assistantMsg: ChatMessageData = {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          cost: response.cost,
          timestamp: new Date().toISOString(),
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
    [caseId, model, provider, selectedKeys]
  )

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  return { messages, isLoading, sendMessage, clearMessages }
}
