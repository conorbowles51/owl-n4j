/** result.corroboration from the engine (backend services/corroborate/engine.py, schema loupe.corroborate/1). */
export type CellState = "present" | "absent" | "no_data"

export interface Instance {
  id: string
  label: string
  start: string
  end: string
  weekday?: number
}

export interface GridRow {
  signal: string
  link_kind: string
  label: string
  cells: Record<string, CellState>
  incident: { present: number; of: number }
  ordinary: { present: number; of: number }
  weight: "full" | "low"
  why_low?: string
  picked_by?: boolean
  context?: boolean
  why_context?: string
  separates: boolean
  records: Record<string, string[]>
  record_counts?: Record<string, number>
}

export interface Check {
  check: string
  outcome: "checked" | "ruled_out" | "weighed_low" | "no_data"
  words: string
  records?: string[]
  open?: boolean
}

export interface NotInPattern {
  who: string
  says: string
  searched: string[]
  counts?: Record<string, number>
  out_of_reach?: string[]
}

export interface Corroboration {
  schema: string
  question: { kind: string; text: string; chips: Record<string, unknown> }
  level: { key: string; name: string; sentence: string; reasons: string[]; rule: string; comparison?: string }
  comparison: { kind: string; words: string; incident: Instance[]; ordinary: Instance[] }
  grid: GridRow[]
  checks: Check[]
  people: { key: string; label: string }[]
  not_in_pattern: NotInPattern[]
  gaps: { missing: string; words: string }[]
  look_further: { text: string; count: number; question: { kind: string; chips: Record<string, unknown> } }[]
  searched?: { records_read: Record<string, number>; kinds_checked: string[]; kinds_with_nothing: string[] }
  seconds?: number
}
