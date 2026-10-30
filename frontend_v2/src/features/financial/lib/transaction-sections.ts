import { useCallback, useState } from "react"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

/**
 * The parts of the Transactions page a person can switch on or off from the control panel. Switching a part
 * off only takes it off the page: it never changes which payments the table lists.
 *
 * Defaults: the page is for reading payments, so the table comes first. Only the money in / money out totals
 * for the payments shown stay on, because they say in one line what the table holds; every chart and summary
 * is one switch away.
 */
export const TRANSACTION_SECTIONS = [
  {
    key: "totals",
    label: "Money in and out",
    hint: "Money in, money out, net and number of payments for what the table shows.",
    on: true,
  },
  {
    key: "months",
    label: "Monthly volume",
    hint: "Money in and out per month. Click a month to show its payments.",
    on: false,
  },
  {
    key: "breakdown",
    label: "Where it went",
    hint: "Tiles by category, person, account or statement. Click one to show its payments.",
    on: false,
  },
  {
    key: "accountTotals",
    label: "Totals per account",
    hint: "Money in and out for each account and bank in view.",
    on: false,
  },
  // These three also live in the table's saved view, so a link that opens Transactions with Charts on (Trends)
  // still does: the saved choice is where each new visit starts.
  {
    key: "charts",
    label: "Charts",
    hint: "Amounts by size, month, category and direction. Click a bar to show its payments.",
    on: false,
    viewKey: "chartsOpen",
  },
  {
    key: "parties",
    label: "From & To",
    hint: "Who paid and who was paid. Pick names to show their payments.",
    on: false,
    viewKey: "partiesOpen",
  },
  {
    key: "flow",
    label: "Money flow",
    hint: "Money in and out around one person or business.",
    on: false,
    viewKey: "flowOpen",
  },
] as const

export type TransactionSectionKey = (typeof TRANSACTION_SECTIONS)[number]["key"]
export type TransactionSections = Record<TransactionSectionKey, boolean>

export const defaultTransactionSections = Object.fromEntries(
  TRANSACTION_SECTIONS.map((section) => [section.key, section.on])
) as TransactionSections

const SECTIONS_KEY = "loupe:transactions:sections:v1"
const PANEL_KEY = "loupe:transactions:controls-open:v1"

function storageKey(base: string, user: string) {
  return `${base}:${user || "anyone"}`
}

/** Saved choices, read defensively: storage can be missing or refused (private windows, insecure contexts). */
export function readTransactionSections(user: string): TransactionSections {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(SECTIONS_KEY, user)) || "{}")
    const sections = { ...defaultTransactionSections }
    for (const key of Object.keys(sections) as TransactionSectionKey[])
      if (typeof saved?.[key] === "boolean") sections[key] = saved[key]
    return sections
  } catch {
    return { ...defaultTransactionSections }
  }
}

export function storeTransactionSections(user: string, sections: TransactionSections) {
  try {
    localStorage.setItem(storageKey(SECTIONS_KEY, user), JSON.stringify(sections))
  } catch {
    // The choice still applies for this visit.
  }
}

export function readControlsOpen(user: string) {
  try {
    return localStorage.getItem(storageKey(PANEL_KEY, user)) === "1"
  } catch {
    return false
  }
}

export function storeControlsOpen(user: string, open: boolean) {
  try {
    localStorage.setItem(storageKey(PANEL_KEY, user), open ? "1" : "0")
  } catch {
    // The choice still applies for this visit.
  }
}

function useStorageUser() {
  return useAuthStore((state) => state.user?.id || state.user?.username || "")
}

/** The page parts switched on for the signed-in person, remembered in this browser. */
export function useTransactionSections() {
  const user = useStorageUser()
  const [state, setState] = useState(() => ({ user, sections: readTransactionSections(user) }))
  // The person can be known only after the first render (sign-in restored from the token): read their choices then.
  const sections = state.user === user ? state.sections : readTransactionSections(user)
  if (state.user !== user) setState({ user, sections })
  const setSection = useCallback(
    (key: TransactionSectionKey, on: boolean) =>
      setState((previous) => {
        const next = { ...previous.sections, [key]: on }
        storeTransactionSections(previous.user, next)
        return { ...previous, sections: next }
      }),
    []
  )
  return [sections, setSection] as const
}

/** Whether the control panel is open, remembered in this browser for the signed-in person. */
export function useControlsOpen() {
  const user = useStorageUser()
  const [state, setState] = useState(() => ({ user, open: readControlsOpen(user) }))
  const open = state.user === user ? state.open : readControlsOpen(user)
  if (state.user !== user) setState({ user, open })
  const setOpen = useCallback(
    (next: boolean) =>
      setState((previous) => {
        storeControlsOpen(previous.user, next)
        return { ...previous, open: next }
      }),
    []
  )
  return [open, setOpen] as const
}
