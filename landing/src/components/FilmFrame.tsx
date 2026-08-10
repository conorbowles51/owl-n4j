import { useEffect, useRef, useState } from "react"
import { usePrefersReducedMotion } from "../lib/useMediaQuery"

interface FilmFrameProps {
  label: string
  poster: string
  mp4: string
  webm?: string
  className?: string
  eager?: boolean
}

export function FilmFrame({
  label,
  poster,
  mp4,
  webm,
  className = "",
  eager = false,
}: FilmFrameProps) {
  const frameRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const reducedMotion = usePrefersReducedMotion()
  const [nearby, setNearby] = useState(eager)
  const [playbackMode, setPlaybackMode] = useState<"auto" | "playing" | "paused">("auto")
  const playing =
    playbackMode === "playing" || (playbackMode === "auto" && !reducedMotion)

  useEffect(() => {
    if (!playing) videoRef.current?.pause()
  }, [playing])

  useEffect(() => {
    const frame = frameRef.current
    if (!frame || typeof IntersectionObserver === "undefined") {
      setNearby(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setNearby(true)
        const video = videoRef.current
        if (!video) return
        if (entry.intersectionRatio >= 0.3 && playing) {
          void video.play().catch(() => undefined)
        } else {
          video.pause()
        }
      },
      { rootMargin: "360px 0px", threshold: [0, 0.3] }
    )
    observer.observe(frame)
    return () => observer.disconnect()
  }, [playing])

  const togglePlayback = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      setPlaybackMode("playing")
      void video.play().catch(() => undefined)
    } else {
      setPlaybackMode("paused")
      video.pause()
    }
  }

  return (
    <div ref={frameRef} className={`film-frame ${className}`}>
      <div className="film-frame-bar" aria-hidden="true">
        <span />
        <span />
        <span />
        <p>{label}</p>
      </div>
      <video
        ref={videoRef}
        aria-label={label}
        poster={poster}
        autoPlay={!reducedMotion}
        muted
        loop
        playsInline
        preload={eager ? "metadata" : "none"}
      >
        {nearby && webm ? <source src={webm} type="video/webm" /> : null}
        {nearby ? <source src={mp4} type="video/mp4" /> : null}
      </video>
      <button className="film-toggle" type="button" onClick={togglePlayback}>
        <span aria-hidden="true">{playing ? "Ⅱ" : "▶"}</span>
        <span className="sr-only">{playing ? `Pause ${label}` : `Play ${label}`}</span>
      </button>
    </div>
  )
}
