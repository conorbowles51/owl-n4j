import type { Tour } from "../tours"
import { HISTORY } from "./common"

// "chat-ask" and "chat-scope" are absent on a chat owned by another person (read-only), so those steps are skipped.
// "case-objective" is the objective banner, shared with the Agent screen. "chat-conversations" and
// "chat-result-graph" are on both the open panel and its folded rail.
export const CHAT_TOUR: Tour = {
  area: "chat",
  name: "Chat",
  steps: [
    { title: "Ask about the case", body: "Type a question in your own words and press Enter to send it.", targets: ['[data-guide="chat-ask"]', "textarea"] },
    { title: "Choose what it reads", body: "Answer from all case data, from the Significant items only, or from the entities you have selected.", targets: ['[data-guide="chat-scope"]'] },
    { title: "The case objective", body: "Answers use the case's saved objective, when it has one. Override for next request changes it for one question only.", targets: ['[data-guide="case-objective"]'] },
    { title: "Your chats", body: "Start a new chat or search earlier ones. All in case shows chats by others on the case.", targets: ['[data-guide="chat-conversations"]'] },
    { title: "What the answer names", body: "The result graph shows the entities an answer names and those found on the way. In the answer, a link opens its payment, graph item or phone record.", targets: ['[data-guide="chat-result-graph"]'] },
    HISTORY,
  ],
}
