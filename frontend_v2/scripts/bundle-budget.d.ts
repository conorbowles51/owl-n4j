import type { Plugin } from "vite"
export const MAIN_GZIP_MAX: number
export function gzipBytes(code: string | Uint8Array): number
export function budgetProblem(fileName: string, gzip: number, max?: number): string | null
export function bundleBudgetPlugin(max?: number): Plugin
export function mainScriptOf(distDir: string): string
