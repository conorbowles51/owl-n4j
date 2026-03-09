import { useState, useCallback } from "react"
import { chatAPI } from "../api"
import { useGraphStore } from "@/stores/graph.store"
import type { ChatMessageData } from "../components/ChatMessage"
import type { ConversationSummary } from "../components/ChatHistoryDrawer"

export function useChat(caseId: string) {
  const [messages, setMessages] = useState<ChatMessageData[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [history] = useState<ConversationSummary[]>([])
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)

  const sendMessage = useCallback(
    async (content: string) => {
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
          selected_keys: Array.from(selectedNodeKeys),
          case_id: caseId,
        })

        const assistantMsg: ChatMessageData = {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          cost: response.cost,
          timestamp: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, assistantMsg])

        // Refresh suggestions
        const sug = await chatAPI.getSuggestions(
          caseId,
          Array.from(selectedNodeKeys)
        )
        setSuggestions(sug.map((s) => s.question))
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
    [caseId, selectedNodeKeys]
  )

  const loadConversation = useCallback((_id: string) => {
    // Will be implemented with conversation persistence
  }, [])

  return {
    messages,
    isLoading,
    suggestions,
    history,
    sendMessage,
    loadConversation,
  }
}
