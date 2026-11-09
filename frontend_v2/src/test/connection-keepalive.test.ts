import { createServer, type Server } from "http"
import { connect } from "net"
import { describe, expect, it } from "vitest"
import { readFileSync } from "fs"
import path from "path"
import { KEEPALIVE_IDLE_MS, connectionKeepalivePlugin } from "../../scripts/connection-keepalive.js"

type Hook = (server: { httpServer: Server }) => void

describe("keepalive on browser connections", () => {
  it("is in the app's server config, for the served app and the dev server", () => {
    const config = readFileSync(path.resolve(__dirname, "../../vite.config.ts"), "utf-8")
    const plugins = config.match(/plugins: \[([^\]]*)\]/)?.[1] ?? ""
    expect(plugins).toContain("connectionKeepalivePlugin()")
    const plugin = connectionKeepalivePlugin()
    expect(typeof plugin.configurePreviewServer).toBe("function")
    expect(typeof plugin.configureServer).toBe("function")
  })

  it("turns keepalive on for each connection, after a minute without traffic", async () => {
    const calls: [boolean, number][] = []
    const server = createServer((_req, res) => res.end("ok"))
    ;(connectionKeepalivePlugin().configurePreviewServer as unknown as Hook)({ httpServer: server })
    server.prependListener("connection", (socket) => {
      const original = socket.setKeepAlive.bind(socket)
      socket.setKeepAlive = (enable?: boolean, delay?: number) => {
        calls.push([Boolean(enable), Number(delay)])
        return original(enable, delay)
      }
    })
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve))
    const port = (server.address() as { port: number }).port
    await new Promise<void>((resolve, reject) => {
      const client = connect(port, "127.0.0.1", () => {
        client.end("GET / HTTP/1.0\r\n\r\n")
      })
      client.on("close", () => resolve())
      client.on("error", reject)
      client.resume()
    })
    await new Promise<void>((resolve) => server.close(() => resolve()))
    expect(KEEPALIVE_IDLE_MS).toBe(60_000)
    expect(calls).toEqual([[true, 60_000]])
  })
})
