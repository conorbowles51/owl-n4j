/** Deep investigation mode (backend services/agent/deep_investigation.py): what the page shows and when it offers it. */

export interface DeepItemProgress {
  id: string
  title: string
  status: "open" | "in_progress" | "done" | "not_done"
  reason?: string | null
  covered: number
  of: number | null
}

export interface DeepProgress {
  schema?: string
  domain: string
  total: number
  closed: number
  open: number
  not_done: number
  notes: number
  items: DeepItemProgress[]
  analyses?: Array<{ approach: string; status: string | null; created: boolean }>
}

/** The cost sentence shown before a deep run starts. The figures are measured per run (STATUS of lx-deepinvest). */
export const DEEP_COST_NOTE =
  "A deep investigation reads the case in full, checks every item on a list, and can take 15 to 40 minutes. It uses several times the model cost of a normal answer. It keeps running if you leave this page, and you can stop it and keep what it has written."

const ASKS_DEEP =
  /\b(deep(ly)?\s+(investigat\w*|report|dive|analysis)|detailed\s+(report|investigat\w*|analysis)|in[- ]depth\s+(report|investigat\w*|analysis)|full\s+(investigat\w*|report)|thorough(ly)?\s+(report|investigat\w*|analysis))/i

/** The words that start a deep run on the server. */
export function asksForDeep(text: string): boolean {
  return ASKS_DEEP.test(text)
}

const BROAD = /\b(everything|all (of )?the|every (phone|account|document)|report|overview|summary of the case|who owns|flag (any|all))\b/i

/** A broad question: the page offers the deep mode (it never switches it on by itself). */
export function looksBroad(text: string): boolean {
  return text.trim().length > 40 && BROAD.test(text) && !asksForDeep(text)
}

export function deepLine(p: DeepProgress): string {
  const open = p.open === 1 ? "1 item open" : `${p.open} items open`
  return `${p.closed} of ${p.total} checklist items closed, ${open}; ${p.notes} findings noted.`
}
