// When vite serves the port (deploy/frontend-server.conf "vite"; nginx has the same in deploy/nginx-loupe-frontend.conf).
// The app is reached through the server's public address, and the cloud network drops a TCP connection that carries
// nothing for 10 minutes. A request the server takes longer than that to answer (Delete now on a folder of 5,000
// files: 807 s on 9 Nov 2026) then never reaches the browser, though the server finished: the browser waits until its
// own limit and reports a failure. Keepalive probes on every browser connection, sent after a minute without traffic,
// keep the connection open for as long as the request runs.
export const KEEPALIVE_IDLE_MS = 60_000

export function keepConnectionsAlive(httpServer, idleMs = KEEPALIVE_IDLE_MS) {
  if (!httpServer) return
  httpServer.on("connection", (socket) => socket.setKeepAlive(true, idleMs))
}

export function connectionKeepalivePlugin(idleMs = KEEPALIVE_IDLE_MS) {
  return {
    name: "loupe-connection-keepalive",
    configureServer(server) {
      keepConnectionsAlive(server.httpServer, idleMs)
    },
    configurePreviewServer(server) {
      keepConnectionsAlive(server.httpServer, idleMs)
    },
  }
}
