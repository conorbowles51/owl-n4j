import { create } from "zustand"
import type {
  ConversationSummary,
  ChatMessageData,
  ResultGraph,
  ResultGraphNode,
  ResultGraphLink,
} from "../types"

type ResultGraphMode = "cumulative" | "last"

interface ChatStore {
  // Conversations
  activeCaseId: string | null
  conversations: ConversationSummary[]
  activeConversationId: string | null
  messages: ChatMessageData[]

  // Result graph
  resultGraphMode: ResultGraphMode
  cumulativeGraph: ResultGraph
  lastResponseGraph: ResultGraph
  selectedResultNodeKey: string | null

  // UI
  conversationPanelOpen: boolean
  resultGraphPanelOpen: boolean

  // Conversation actions
  setActiveCaseId: (id: string | null) => void
  setConversations: (conversations: ConversationSummary[]) => void
  setActiveConversation: (id: string | null) => void
  setMessages: (messages: ChatMessageData[]) => void
  addMessage: (msg: ChatMessageData) => void
  clearMessages: () => void

  // Result graph actions
  setResultGraphMode: (mode: ResultGraphMode) => void
  appendResultGraph: (graph: ResultGraph) => void
  setLastResponseGraph: (graph: ResultGraph) => void
  clearResultGraphs: () => void
  setSelectedResultNodeKey: (key: string | null) => void

  // UI actions
  setConversationPanelOpen: (open: boolean) => void
  setResultGraphPanelOpen: (open: boolean) => void
}

const EMPTY_GRAPH: ResultGraph = { nodes: [], links: [] }

function mergeGraphs(existing: ResultGraph, incoming: ResultGraph): ResultGraph {
  const nodeMap = new Map<string, ResultGraphNode>()

  // Add existing nodes
  for (const node of existing.nodes) {
    nodeMap.set(node.key, node)
  }

  // Merge incoming nodes — keep higher confidence
  for (const node of incoming.nodes) {
    const prev = nodeMap.get(node.key)
    if (!prev || node.confidence > prev.confidence) {
      nodeMap.set(node.key, node)
    }
  }

  // Deduplicate links by source+target+type
  const linkSet = new Set<string>()
  const links: ResultGraphLink[] = []

  const addLink = (link: ResultGraphLink) => {
    const linkKey = `${link.source}::${link.target}::${link.type}`
    if (!linkSet.has(linkKey)) {
      linkSet.add(linkKey)
      links.push(link)
    }
  }

  for (const link of existing.links) addLink(link)
  for (const link of incoming.links) addLink(link)

  return { nodes: Array.from(nodeMap.values()), links }
}

export const useChatStore = create<ChatStore>((set) => ({
  // Initial state
  activeCaseId: null,
  conversations: [],
  activeConversationId: null,
  messages: [],
  resultGraphMode: "cumulative",
  cumulativeGraph: EMPTY_GRAPH,
  lastResponseGraph: EMPTY_GRAPH,
  selectedResultNodeKey: null,
  conversationPanelOpen: true,
  resultGraphPanelOpen: true,

  // Conversation actions
  setActiveCaseId: (id) => set({ activeCaseId: id }),
  setConversations: (conversations) => set({ conversations }),
  setActiveConversation: (id) => set({ activeConversationId: id }),
  setMessages: (messages) => set({ messages }),
  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),
  clearMessages: () =>
    set({
      messages: [],
      cumulativeGraph: EMPTY_GRAPH,
      lastResponseGraph: EMPTY_GRAPH,
      selectedResultNodeKey: null,
    }),

  // Result graph actions
  setResultGraphMode: (mode) => set({ resultGraphMode: mode }),
  appendResultGraph: (graph) =>
    set((state) => ({
      cumulativeGraph: mergeGraphs(state.cumulativeGraph, graph),
      lastResponseGraph: graph,
    })),
  setLastResponseGraph: (graph) => set({ lastResponseGraph: graph }),
  clearResultGraphs: () =>
    set({
      cumulativeGraph: EMPTY_GRAPH,
      lastResponseGraph: EMPTY_GRAPH,
      selectedResultNodeKey: null,
    }),
  setSelectedResultNodeKey: (key) => set({ selectedResultNodeKey: key }),

  // UI actions
  setConversationPanelOpen: (open) => set({ conversationPanelOpen: open }),
  setResultGraphPanelOpen: (open) => set({ resultGraphPanelOpen: open }),
}))
