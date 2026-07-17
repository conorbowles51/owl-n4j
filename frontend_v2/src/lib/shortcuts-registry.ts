export type ShortcutScope =
  | "global"
  | "page:graph"
  | "page:timeline"
  | "page:table"

export interface ShortcutDef {
  id: string
  keys: string
  ariaKeyShortcuts?: string
  description: string
  scope: ShortcutScope
  implemented: boolean
  showInSettings: boolean
}

export const CASE_VIEW_SHORTCUTS = [
  {
    view: "graph",
    label: "Graph",
    key: "1",
    code: "Digit1",
    keys: "Ctrl/Cmd+Shift+1",
    ariaKeyShortcuts: "Control+Shift+1 Meta+Shift+1",
  },
  {
    view: "timeline",
    label: "Timeline",
    key: "2",
    code: "Digit2",
    keys: "Ctrl/Cmd+Shift+2",
    ariaKeyShortcuts: "Control+Shift+2 Meta+Shift+2",
  },
  {
    view: "map",
    label: "Map",
    key: "3",
    code: "Digit3",
    keys: "Ctrl/Cmd+Shift+3",
    ariaKeyShortcuts: "Control+Shift+3 Meta+Shift+3",
  },
  {
    view: "table",
    label: "Table",
    key: "4",
    code: "Digit4",
    keys: "Ctrl/Cmd+Shift+4",
    ariaKeyShortcuts: "Control+Shift+4 Meta+Shift+4",
  },
  {
    view: "financial",
    label: "Financial",
    key: "5",
    code: "Digit5",
    keys: "Ctrl/Cmd+Shift+5",
    ariaKeyShortcuts: "Control+Shift+5 Meta+Shift+5",
  },
  {
    view: "cellebrite",
    label: "Cellebrite",
    key: "6",
    code: "Digit6",
    keys: "Ctrl/Cmd+Shift+6",
    ariaKeyShortcuts: "Control+Shift+6 Meta+Shift+6",
  },
  {
    view: "profiles",
    label: "Profiles",
    key: "7",
    code: "Digit7",
    keys: "Ctrl/Cmd+Shift+7",
    ariaKeyShortcuts: "Control+Shift+7 Meta+Shift+7",
  },
  {
    view: "evidence",
    label: "Evidence",
    key: "8",
    code: "Digit8",
    keys: "Ctrl/Cmd+Shift+8",
    ariaKeyShortcuts: "Control+Shift+8 Meta+Shift+8",
  },
] as const

export type CaseViewShortcut = (typeof CASE_VIEW_SHORTCUTS)[number]
export type CaseViewId = CaseViewShortcut["view"]

const caseViewShortcutDefs: ShortcutDef[] = CASE_VIEW_SHORTCUTS.map(
  (shortcut) => ({
    id: `global.case-view.${shortcut.view}`,
    keys: shortcut.keys,
    ariaKeyShortcuts: shortcut.ariaKeyShortcuts,
    description: `${shortcut.label} view`,
    scope: "global",
    implemented: true,
    showInSettings: true,
  })
)

export const SHORTCUTS: ShortcutDef[] = [
  {
    id: "global.chat-panel",
    keys: "Ctrl+Shift+L",
    ariaKeyShortcuts: "Control+Shift+L",
    description: "Toggle chat panel",
    scope: "global",
    implemented: true,
    showInSettings: true,
  },
  ...caseViewShortcutDefs,
  {
    id: "graph.select-all",
    keys: "Ctrl/Cmd+A",
    ariaKeyShortcuts: "Control+A Meta+A",
    description: "Select all visible graph nodes",
    scope: "page:graph",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "graph.clear-selection",
    keys: "Escape",
    ariaKeyShortcuts: "Escape",
    description: "Clear graph selection",
    scope: "page:graph",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.next-event",
    keys: "Down or J",
    ariaKeyShortcuts: "ArrowDown J",
    description: "Move to next timeline event",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.previous-event",
    keys: "Up or K",
    ariaKeyShortcuts: "ArrowUp K",
    description: "Move to previous timeline event",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.open-event",
    keys: "Enter or Space",
    ariaKeyShortcuts: "Enter Space",
    description: "Open focused timeline event",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.clear-selection",
    keys: "Escape",
    ariaKeyShortcuts: "Escape",
    description: "Clear timeline selection or blur search",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.previous-cluster",
    keys: "Ctrl+Shift+Left",
    ariaKeyShortcuts: "Control+Shift+ArrowLeft",
    description: "Move to previous timeline cluster",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.next-cluster",
    keys: "Ctrl+Shift+Right",
    ariaKeyShortcuts: "Control+Shift+ArrowRight",
    description: "Move to next timeline cluster",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.toggle-filters",
    keys: "[ or ]",
    ariaKeyShortcuts: "[ ]",
    description: "Toggle timeline filters",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "timeline.focus-search",
    keys: "/",
    ariaKeyShortcuts: "/",
    description: "Focus timeline search",
    scope: "page:timeline",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "table.next-row",
    keys: "Down or J",
    ariaKeyShortcuts: "ArrowDown J",
    description: "Move to next table row",
    scope: "page:table",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "table.previous-row",
    keys: "Up or K",
    ariaKeyShortcuts: "ArrowUp K",
    description: "Move to previous table row",
    scope: "page:table",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "table.open-row",
    keys: "Enter",
    ariaKeyShortcuts: "Enter",
    description: "Open focused table row",
    scope: "page:table",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "table.toggle-row",
    keys: "Space",
    ariaKeyShortcuts: "Space",
    description: "Toggle focused table row",
    scope: "page:table",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "table.select-all",
    keys: "Ctrl/Cmd+A",
    ariaKeyShortcuts: "Control+A Meta+A",
    description: "Select all visible table rows",
    scope: "page:table",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "table.clear-selection",
    keys: "Escape",
    ariaKeyShortcuts: "Escape",
    description: "Clear table selection or blur search",
    scope: "page:table",
    implemented: true,
    showInSettings: true,
  },
  {
    id: "table.focus-search",
    keys: "/",
    ariaKeyShortcuts: "/",
    description: "Focus table search",
    scope: "page:table",
    implemented: true,
    showInSettings: true,
  },
]

export const SETTINGS_SHORTCUTS = SHORTCUTS.filter(
  (shortcut) => shortcut.showInSettings
)
