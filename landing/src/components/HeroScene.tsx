import { useEffect, useRef } from "react"
import { LoupeField } from "../three/LoupeField"

export function HeroScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    let field: LoupeField

    try {
      field = new LoupeField(canvas, { reducedMotion })
    } catch {
      canvas.dataset.webgl = "unavailable"
      return
    }

    let visible = true
    const sync = () => {
      if (visible && !document.hidden) field.start()
      else field.stop()
    }
    const resizeObserver = new ResizeObserver(() => field.resize())
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
      field.setPointer(
        (event.clientX / window.innerWidth) * 2 - 1,
        (event.clientY / window.innerHeight) * 2 - 1
      )
    }
    const onScroll = () => field.setScroll(window.scrollY / Math.max(window.innerHeight, 1))
    const onVisibility = () => sync()
    window.addEventListener("pointermove", onPointerMove, { passive: true })
    window.addEventListener("scroll", onScroll, { passive: true })
    document.addEventListener("visibilitychange", onVisibility)
    onScroll()
    sync()

    return () => {
      window.removeEventListener("pointermove", onPointerMove)
      window.removeEventListener("scroll", onScroll)
      document.removeEventListener("visibilitychange", onVisibility)
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      field.destroy()
    }
  }, [])

  return <canvas ref={canvasRef} className="hero-canvas" aria-hidden="true" />
}
