import { useEffect, useState } from "react"
import { ImageOff, Loader2 } from "lucide-react"
import { cn } from "@/lib/cn"

export function EvidenceImage({
  url,
  alt,
  focalX = 0.5,
  focalY = 0.5,
  className,
}: {
  url: string
  alt: string
  focalX?: number | null
  focalY?: number | null
  className?: string
}) {
  const [source, setSource] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    void fetch(url, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("authToken") ?? ""}`,
      },
      credentials: "include",
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error()
        return response.blob()
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setSource(objectUrl)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url])
  if (failed)
    return (
      <div
        className={cn("flex items-center justify-center bg-muted", className)}
      >
        <ImageOff className="size-5 text-muted-foreground" />
      </div>
    )
  if (!source)
    return (
      <div
        className={cn("flex items-center justify-center bg-muted", className)}
      >
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      </div>
    )
  return (
    <img
      src={source}
      alt={alt}
      className={cn("object-cover", className)}
      style={{
        objectPosition: `${(focalX ?? 0.5) * 100}% ${(focalY ?? 0.5) * 100}%`,
      }}
    />
  )
}
