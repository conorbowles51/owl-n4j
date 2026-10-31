// Runs the graph canvas's warm-up layout steps off the page's main thread (see warmupLayout).
// While it works it sends the positions reached so far (step 0, then about once a second) so the
// canvas can show the graph being arranged; the last message holds the positions after every step.
import { warmupLayout, type LayoutMessage, type WarmupLink, type WarmupNode, type WarmupParams } from "./warmup-layout"

const PROGRESS_INTERVAL_MS = 1000

self.onmessage = (event: MessageEvent<{ nodes: WarmupNode[]; links: WarmupLink[]; params: WarmupParams }>) => {
  const { nodes, links, params } = event.data
  const post = (message: LayoutMessage) => self.postMessage(message, { transfer: [message.positions.buffer] })
  let lastSent = 0
  const positions = warmupLayout(nodes, links, params, (step, read) => {
    if (step === params.ticks) return // the final positions follow
    const now = performance.now()
    if (step === 0 || now - lastSent >= PROGRESS_INTERVAL_MS) {
      lastSent = now
      post({ positions: read(), step, done: false })
    }
  })
  post({ positions, step: params.ticks, done: true })
}
