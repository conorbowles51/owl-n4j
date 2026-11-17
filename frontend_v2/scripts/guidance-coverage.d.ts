export interface ScannedControl {
  file: string
  line: number
  tag: string
  kind: string
  iconOnly: boolean
  spread: boolean
  name: string
  hasName: boolean
  hasTooltip: boolean
  inTrigger: boolean
  title: boolean
  disabled: boolean
  disabledWhy: boolean
  disabledExpr: string
  guide: string
}
export interface ScannedFile {
  file: string
  controls: ScannedControl[]
  guides: string[]
  terms: { line: number; term: string }[]
  dialogs: { line: number; title: string }[]
}
export function screenFiles(srcDir: string): string[]
export function scanFile(file: string, srcDir: string): ScannedFile
export function scanAll(srcDir: string): ScannedFile[]
export function iconGaps(results: ScannedFile[], allow?: Record<string, string>): ScannedControl[]
export function guideTargets(results: ScannedFile[]): Set<string>
export function headingSlugs(markdown: string): Set<string>
export function disabledGaps(results: ScannedFile[], allow?: Record<string, string>): ScannedControl[]
export function caseRoutes(srcDir: string): string[]
