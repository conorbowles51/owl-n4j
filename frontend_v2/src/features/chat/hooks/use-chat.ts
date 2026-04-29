import { useCallback, useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { chatAPI, chatHistoryAPI } from "../api"
import { useChatStore } from "../stores/chat.store"
import { useGraphStore } from "@/stores/graph.store"
import { CONVERSATIONS_KEY } from "./use-conversations"
import type { ChatMessageData, ChatScope } from "../types"

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
  const activeCaseId = useChatStore((s) => s.activeCaseId)
  const activeConversationId = useChatStore((s) => s.activeConversationId)
  const setActiveCaseId = useChatStore((s) => s.setActiveCaseId)
  const setActiveConversation = useChatStore((s) => s.setActiveConversation)

  const refreshSuggestions = useCallback(
    async (scope: ChatScope = "case_overview") => {
      try {
        const next = await chatAPI.getSuggestions(
          caseId,
          scope === "selection" ? Array.from(selectedNodeKeys) : undefined
        )
        setSuggestions(next.map((item) => item.question))
      } catch {
        setSuggestions([])
      }
    },
    [caseId, selectedNodeKeys]
  )

  useEffect(() => {
    if (activeCaseId !== caseId) {
      clearMessages()
      savedConversationId.current = null
      setActiveConversation(null)
      setActiveCaseId(caseId)
    }
    setSuggestions([])
    void refreshSuggestions("case_overview")
  }, [
    activeCaseId,
    caseId,
    clearMessages,
    refreshSuggestions,
    setActiveCaseId,
    setActiveConversation,
  ])

  const sendMessage = useCallback(
    async (
      content: string,
      model?: string,
      provider?: string,
      scope: ChatScope = "case_overview"
    ) => {
      const effectiveScope =
        scope === "selection" && selectedNodeKeys.size > 0
          ? "selection"
          : "case_overview"
      const selectedKeys =
        effectiveScope === "selection" ? Array.from(selectedNodeKeys) : undefined

      const userMsg: ChatMessageData = {
        role: "user",
        content,
        scope: effectiveScope,
        selected_entity_keys: selectedKeys,
        timestamp: new Date().toISOString(),
      }
      addMessage(userMsg)
      setIsLoading(true)

      try {
        const response = await chatAPI.ask({
          question: content,
          case_id: caseId,
          conversation_id: savedConversationId.current || activeConversationId || undefined,
          scope: effectiveScope,
          selected_entity_keys: selectedKeys,
          persist: true,
          ...(model ? { model } : {}),
          ...(provider ? { provider } : {}),
        })

        const assistantMsg: ChatMessageData = {
          id: response.message_id,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          cost: response.cost,
          timestamp: new Date().toISOString(),
          model_info: response.model_info,
          resultGraph: response.result_graph ?? undefined,
          provenance: response.provenance,
        }
        addMessage(assistantMsg)

        if (response.result_graph) {
          appendResultGraph(response.result_graph)
        }

        if (response.conversation_id) {
          savedConversationId.current = response.conversation_id
          setActiveConversation(response.conversation_id)
        }

        setSuggestions(response.suggestions.map((item) => item.question))
        queryClient.invalidateQueries({ queryKey: CONVERSATIONS_KEY })
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
    [
      activeConversationId,
      addMessage,
      appendResultGraph,
      caseId,
      queryClient,
      selectedNodeKeys,
      setActiveConversation,
    ]
  )

  const loadConversation = useCallback(
    async (id: string) => {
      try {
        const conv = await chatHistoryAPI.get(id)
        setMessages(conv.messages)
        setActiveConversation(id)
        savedConversationId.current = id

        const store = useChatStore.getState()
        store.clearResultGraphs()
        for (const msg of conv.messages) {
          if (msg.resultGraph) {
            store.appendResultGraph(msg.resultGraph)
          }
        }

        void refreshSuggestions("case_overview")
      } catch {
        // Ignore load failures.
      }
    },
    [refreshSuggestions, setMessages, setActiveConversation]
  )

  const startNewConversation = useCallback(() => {
    clearMessages()
    savedConversationId.current = null
    setActiveConversation(null)
    void refreshSuggestions("case_overview")
  }, [clearMessages, refreshSuggestions, setActiveConversation])

  return {
    messages,
    isLoading,
    suggestions,
    sendMessage,
    loadConversation,
    startNewConversation,
  }
}
