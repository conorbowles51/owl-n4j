import { useState, type ReactNode } from "react"
import { Check, Loader2, RotateCcw, Search } from "lucide-react"
import { toast } from "sonner"
import type { QueryKey } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"
import { useLocationCorrection } from "../hooks/use-location-correction"
import type { LocationCorrectionResult } from "../api"

interface LocationCorrectionInlineProps {
  caseId: string
  nodeKey: string | null | undefined
  sourceView: string
  currentAddress?: string | null
  currentLatitude?: number | null
  currentLongitude?: number | null
  currentConfidence?: string | null
  className?: string
  compact?: boolean
  extraInvalidateKeys?: QueryKey[]
  actions?: ReactNode
  onPreview?: (result: LocationCorrectionResult) => void
  onApplied?: (result: LocationCorrectionResult) => void
  onUndone?: (result: LocationCorrectionResult) => void
}

function formatCoordinate(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(5) : null
}

function resultCoordinates(result: LocationCorrectionResult | null) {
  const latitude = formatCoordinate(result?.latitude)
  const longitude = formatCoordinate(result?.longitude)
  return latitude && longitude ? `${latitude}, ${longitude}` : null
}

export function LocationCorrectionInline({
  caseId,
  nodeKey,
  sourceView,
  currentAddress,
  currentLatitude,
  currentLongitude,
  currentConfidence,
  className,
  compact = false,
  extraInvalidateKeys,
  actions,
  onPreview,
  onApplied,
  onUndone,
}: LocationCorrectionInlineProps) {
  const [address, setAddress] = useState("")
  const [previewResult, setPreviewResult] = useState<LocationCorrectionResult | null>(null)
  const [previewAddress, setPreviewAddress] = useState("")
  const [localConfidence, setLocalConfidence] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const correction = useLocationCorrection({
    caseId,
    nodeKey,
    sourceView,
    extraInvalidateKeys,
    onApplied: (result) => {
      setLocalConfidence(result.confidence ?? "manual")
      onApplied?.(result)
    },
    onUndone: (result) => {
      setLocalConfidence(result.confidence ?? null)
      onUndone?.(result)
    },
  })

  const trimmedAddress = address.trim()
  const canApply = Boolean(previewResult?.success && previewAddress === trimmedAddress)
  const displayConfidence = localConfidence ?? currentConfidence ?? null
  const currentCoords = (() => {
    const latitude = formatCoordinate(currentLatitude)
    const longitude = formatCoordinate(currentLongitude)
    return latitude && longitude ? `${latitude}, ${longitude}` : null
  })()
  const previewCoords = resultCoordinates(previewResult)
  const canUndo = displayConfidence === "manual" || Boolean(previewResult?.undo_key)

  const handlePreview = async () => {
    if (!trimmedAddress) return
    setError(null)
    try {
      const result = await correction.preview(trimmedAddress)
      if (!result.success) {
        setPreviewResult(null)
        setPreviewAddress("")
        setError(result.error ?? "Could not geocode address.")
        return
      }
      setPreviewResult(result)
      setPreviewAddress(trimmedAddress)
      onPreview?.(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not geocode address.")
    }
  }

  const handleApply = async () => {
    if (!canApply || !trimmedAddress) return
    setError(null)
    try {
      const result = await correction.apply(trimmedAddress)
      if (!result.success) {
        setError(result.error ?? "Could not apply location.")
        return
      }
      setPreviewResult(result)
      setPreviewAddress(trimmedAddress)
      setAddress("")
      toast.success("Location corrected")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply location.")
    }
  }

  const handleUndo = async () => {
    setError(null)
    try {
      await correction.undo()
      setAddress("")
      setPreviewResult(null)
      setPreviewAddress("")
      toast.success("Location restored")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not undo location correction.")
    }
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className={cn("flex gap-2", compact && "gap-1.5")}>
        <Input
          value={address}
          onChange={(event) => {
            setAddress(event.target.value)
            setError(null)
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault()
              void handlePreview()
            }
          }}
          placeholder="Correct address"
          disabled={!nodeKey || correction.isApplying || correction.isUndoing}
          className={compact ? "h-7 text-xs" : undefined}
        />
        <Button
          type="button"
          variant="outline"
          size={compact ? "icon-sm" : "icon"}
          onClick={handlePreview}
          disabled={!nodeKey || !trimmedAddress || correction.isPreviewing || correction.isApplying}
          title="Preview location"
        >
          {correction.isPreviewing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Search className="size-4" />
          )}
        </Button>
        <Button
          type="button"
          variant="primary"
          size={compact ? "icon-sm" : "icon"}
          onClick={handleApply}
          disabled={!nodeKey || !canApply || correction.isApplying}
          title="Apply location"
        >
          {correction.isApplying ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Check className="size-4" />
          )}
        </Button>
        {canUndo && (
          <Button
            type="button"
            variant="ghost"
            size={compact ? "icon-sm" : "icon"}
            onClick={handleUndo}
            disabled={!nodeKey || correction.isUndoing}
            title="Undo last relocation"
          >
            {correction.isUndoing ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RotateCcw className="size-4" />
            )}
          </Button>
        )}
        {actions}
      </div>

      {(currentAddress || currentCoords || displayConfidence) && (
        <div className="space-y-1 text-[11px] leading-relaxed text-muted-foreground">
          {currentAddress && <div className="line-clamp-2">{currentAddress}</div>}
          <div className="flex flex-wrap items-center gap-1.5">
            {currentCoords && <span className="font-mono">{currentCoords}</span>}
            {displayConfidence && (
              <Badge variant="outline" className="px-1 py-0 text-[9px]">
                {displayConfidence}
              </Badge>
            )}
          </div>
        </div>
      )}

      {previewResult?.success && previewCoords && (
        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-2 py-1.5 text-[11px] leading-relaxed">
          <div className="font-medium text-foreground">
            {previewResult.formatted_address || previewAddress}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-muted-foreground">
            <span className="font-mono">{previewCoords}</span>
            {previewResult.geocoder_confidence && (
              <Badge variant="outline" className="px-1 py-0 text-[9px]">
                {previewResult.geocoder_confidence}
              </Badge>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-[11px] text-destructive">
          {error}
        </div>
      )}
    </div>
  )
}
