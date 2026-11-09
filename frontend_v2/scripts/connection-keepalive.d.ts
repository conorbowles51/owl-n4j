import type { Plugin } from "vite"
export const KEEPALIVE_IDLE_MS: number
export function keepConnectionsAlive(httpServer: { on(event: "connection", cb: (socket: { setKeepAlive(enable: boolean, delay: number): unknown }) => void): unknown } | null | undefined, idleMs?: number): void
export function connectionKeepalivePlugin(idleMs?: number): Plugin
