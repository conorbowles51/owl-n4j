import { useState, useCallback, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { chatAPI, chatHistoryAPI } from "../api"
import { useChatStore } from "../stores/chat.store"
import { useGraphStore } from "@/stores/graph.store"
import { CONVERSATIONS_KEY } from "./use-conversations"
import type { ChatMessageData } from "../types"

export function useChat(caseId: string) {
  const queryClient = useQueryClient()
  const [isLoading, setIsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const savedConversationId = useRef<string | null>(null)

  const messages = useChatStore((s) => s.messages)
  const addMessage = useChatStore((s) => s.addMessage)
  const setMessages = useChatStore((s) => s.setMessages)
  const clearMessages = useChatStore((s) => s.clearMessages)
  const appendResultGraph = useChatStore((s) => s.appendResultGraph)
  const activeConversationId = useChatStore((s) => s.activeConversationId)
  const setActiveConversation = useChatStore((s) => s.setActiveConversation)

  const autoSave = useCallback(
    async (allMessages: ChatMessageData[], title?: string) => {
      try {
        const convId = savedConversationId.current || activeConversationId
        if (convId) {
          // Update existing conversation
          await chatHistoryAPI.update(convId, {
            messages: allMessages,
            ...(title ? { name: title } : {}),
          })
        } else {
          // Create new conversation
          const autoTitle =
            title ||
            allMessages[0]?.content.slice(0, 50) ||
            "New conversation"
          const conv = await chatHistoryAPI.create({
            name: autoTitle,
            messages: allMessages,
            case_id: caseId,
          })
          savedConversationId.current = conv.id
          setActiveConversation(conv.id)
          queryClient.invalidateQueries({ queryKey: CONVERSATIONS_KEY })
        }
      } catch {
        // Silent fail — don't block chat for save errors
      }
    },
    [caseId, activeConversationId, setActiveConversation]
  )

  const sendMessage = useCallback(
    async (content: string, model?: string, provider?: string) => {
      const userMsg: ChatMessageData = {
        role: "user",
        content,
        timestamp: new Date().toISOString(),
      }
      addMessage(userMsg)
      setIsLoading(true)

      try {
        const response = await chatAPI.ask({
          question: content,
          selected_keys: Array.from(selectedNodeKeys),
          case_id: caseId,
          ...(model ? { model } : {}),
          ...(provider ? { provider } : {}),
        })

        const assistantMsg: ChatMessageData = {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          cost: response.cost,
          timestamp: new Date().toISOString(),
          model_info: response.model_info,
          resultGraph: response.result_graph ?? undefined,
        }
        addMessage(assistantMsg)

        // Merge result graph into cumulative
        if (response.result_graph) {
          appendResultGraph(response.result_graph)
        }

        // Auto-save after AI response
        const allMessages = [
          ...useChatStore.getState().messages,
        ]
        await autoSave(allMessages)

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
        addMessage(errorMsg)
      } finally {
        setIsLoading(false)
      }
    },
    [caseId, selectedNodeKeys, addMessage, appendResultGraph, autoSave]
  )

  const loadConversation = useCallback(
    async (id: string) => {
      try {
        const conv = await chatHistoryAPI.get(id)
        setMessages(conv.messages)
        setActiveConversation(id)
        savedConversationId.current = id

        // Rebuild cumulative graph from loaded messages
        const store = useChatStore.getState()
        store.clearResultGraphs()
        for (const msg of conv.messages) {
          if (msg.resultGraph) {
            store.appendResultGraph(msg.resultGraph)
          }
        }

        // Refresh suggestions
        const sug = await chatAPI.getSuggestions(
          caseId,
          Array.from(selectedNodeKeys)
        )
        setSuggestions(sug.map((s) => s.question))
      } catch {
        // Failed to load conversation
      }
    },
    [caseId, selectedNodeKeys, setMessages, setActiveConversation]
  )

  const startNewConversation = useCallback(() => {
    clearMessages()
    savedConversationId.current = null
    setActiveConversation(null)
    setSuggestions([])
  }, [clearMessages, setActiveConversation])

  return {
    messages,
    isLoading,
    suggestions,
    sendMessage,
    loadConversation,
    startNewConversation,
  }
}
