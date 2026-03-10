import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { chatHistoryAPI } from "../api"
import type { CreateChatHistory } from "../types"

export const CONVERSATIONS_KEY = ["chat-history"]

export function useConversations() {
  return useQuery({
    queryKey: CONVERSATIONS_KEY,
    queryFn: chatHistoryAPI.list,
  })
}

export function useConversation(chatId: string | null) {
  return useQuery({
    queryKey: [...CONVERSATIONS_KEY, chatId],
    queryFn: () => chatHistoryAPI.get(chatId!),
    enabled: !!chatId,
  })
}

export function useCreateConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateChatHistory) => chatHistoryAPI.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY }),
  })
}

export function useUpdateConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      chatId,
      data,
    }: {
      chatId: string
      data: Partial<CreateChatHistory>
    }) => chatHistoryAPI.update(chatId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY }),
  })
}

export function useDeleteConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (chatId: string) => chatHistoryAPI.delete(chatId),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY }),
  })
}
