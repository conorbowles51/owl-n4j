// Runs the graph canvas's warm-up layout steps off the page's main thread (see warmupLayout).
import { warmupLayout, type WarmupLink, type WarmupNode, type WarmupParams } from "./warmup-layout"

self.onmessage = (event: MessageEvent<{ nodes: WarmupNode[]; links: WarmupLink[]; params: WarmupParams }>) => {
  const { nodes, links, params } = event.data
  const positions = warmupLayout(nodes, links, params)
  self.postMessage({ positions }, { transfer: [positions.buffer] })
}
