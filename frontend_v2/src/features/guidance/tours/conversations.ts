import type { Tour } from "../tours"

// "conversations-list" is the open list; on a narrow screen it folds into a rail (thread-rail), the fallback target.
// "conversations-review" renders once the thread counts load; "conversations-strip" only when the scope has messages.
export const CONVERSATIONS_TOUR: Tour = {
  area: "conversations",
  name: "Conversations",
  steps: [
    { title: "Threads or people", body: "Pick a thread to read it. Switch to People to read every message with one person, across threads.", targets: ['[data-guide="conversations-list"]', '[data-testid="thread-rail"]'] },
    { title: "Narrow the messages", body: "Filter by app, kind, direction, deleted state, attachment, dates or the words a message contains.", targets: ['[data-guide="conversations-filters"]'] },
    { title: "Keep track of review", body: "This counts the threads not yet reviewed. Split for review shares the threads out as Workspace tasks.", targets: ['[data-guide="conversations-review"]'] },
    { title: "Act on what you select", body: "Select messages, then ask about them, write a note about them or add them to a dossier, theory or timeline.", targets: ['[data-guide="conversations-actions"]'] },
    { title: "Messages by day", body: "Each bar is one day's messages. Click a day to jump to it.", targets: ['[data-guide="conversations-strip"]'] },
    { title: "Words also on other phones", body: "Tick Mark what also appears elsewhere to mark messages whose words appear on other phones. A stock phrase is shown but counted for nothing.", targets: ['[data-guide="also-elsewhere"]'] },
  ],
}
