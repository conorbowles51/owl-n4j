import "@testing-library/jest-dom/vitest"

/**
 * jsdom ships no canvas implementation, and reports the missing getContext
 * through its virtual console — which React's act() then surfaces as a test
 * failure. The reduction beat draws to canvas, so stub enough of the 2D
 * context for it to run. Nothing here asserts on drawing; the beat's copy
 * carries its argument without the canvas.
 */
const noop = () => {}

/** Reveal observes intersection; jsdom has no implementation. */
class StubIntersectionObserver {
  readonly root = null
  readonly rootMargin = ""
  readonly thresholds: ReadonlyArray<number> = []
  observe = noop
  unobserve = noop
  disconnect = noop
  takeRecords = () => []
}

globalThis.IntersectionObserver =
  StubIntersectionObserver as unknown as typeof IntersectionObserver

HTMLCanvasElement.prototype.getContext = function getContext(this: HTMLCanvasElement) {
  return {
    canvas: this,
    setTransform: noop,
    clearRect: noop,
    beginPath: noop,
    arc: noop,
    fill: noop,
    moveTo: noop,
    lineTo: noop,
    stroke: noop,
    globalAlpha: 1,
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
  } as unknown as CanvasRenderingContext2D
} as unknown as HTMLCanvasElement["getContext"]
