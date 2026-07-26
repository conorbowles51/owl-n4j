import { useEffect, useRef } from "react"
import type { LoupeField } from "../three/LoupeField"

export function HeroScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let field: LoupeField | null = null
    let disposed = false
    let teardown = () => {}

    const initialize = async () => {
      try {
        const { LoupeField: LoupeFieldRuntime } = await import("../three/LoupeField")
        if (disposed) return

        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
        field = new LoupeFieldRuntime(canvas, { reducedMotion })
        let visible = true

        const sync = () => {
          if (!field) return
          if (visible && !document.hidden) field.start()
          else field.stop()
        }
        const resizeObserver = new ResizeObserver(() => field?.resize())
        if (canvas.parentElement) resizeObserver.observe(canvas.parentElement)

        const intersectionObserver = new IntersectionObserver(
          ([entry]) => {
            visible = entry?.isIntersecting ?? true
            sync()
          },
          { rootMargin: "120px" }
        )
        intersectionObserver.observe(canvas)

        const onPointerMove = (event: PointerEvent) => {
          field?.setPointer(
            (event.clientX / window.innerWidth) * 2 - 1,
            (event.clientY / window.innerHeight) * 2 - 1
          )
        }
        const onScroll = () =>
          field?.setScroll(window.scrollY / Math.max(window.innerHeight, 1))
        const onVisibility = () => sync()

        window.addEventListener("pointermove", onPointerMove, { passive: true })
        window.addEventListener("scroll", onScroll, { passive: true })
        document.addEventListener("visibilitychange", onVisibility)
        onScroll()
        sync()

        teardown = () => {
          window.removeEventListener("pointermove", onPointerMove)
          window.removeEventListener("scroll", onScroll)
          document.removeEventListener("visibilitychange", onVisibility)
          resizeObserver.disconnect()
          intersectionObserver.disconnect()
        }
      } catch {
        canvas.dataset.webgl = "unavailable"
      }
    }

    void initialize()

    return () => {
      disposed = true
      teardown()
      field?.destroy()
    }
  }, [])

  return <canvas ref={canvasRef} className="hero-canvas" aria-hidden="true" />
}
