import { useEffect, useMemo, useRef, useState } from "react"
import type { LucideIcon } from "lucide-react"
import { CheckCircle2, Tag, User } from "lucide-react"

import { cn } from "@/lib/cn"
import { useProtectedObjectUrl } from "@/lib/protected-file"

import type { PhoneReport } from "../../types"
import { readText } from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { reportMaps } from "../events/eventUtils"
import {
  type CellebriteFileRecord,
  CATEGORY_ICONS,
  categoryColor,
  evidenceUrl,
  fileBadges,
  fileCategory,
  fileId,
  fileName,
  fileParentLabel,
  fileSize,
  fileTags,
  linkedEntityIds,
  reportKeyOfFile,
  videoFrameUrl,
} from "./filesUtils"

export function FileThumbnail({
  file,
  reports,
  selected,
  layout,
  onToggleSelect,
  onOpen,
}: {
  file: CellebriteFileRecord
  reports: PhoneReport[]
  selected: boolean
  layout: "grid" | "list"
  onToggleSelect: (shiftKey?: boolean) => void
  onOpen: () => void
}) {
  const [imageFailed, setImageFailed] = useState(false)
  const [shouldLoadThumbnail, setShouldLoadThumbnail] = useState(false)
  const itemRef = useRef<HTMLButtonElement | null>(null)
  const id = fileId(file)
  const name = fileName(file)
  const category = fileCategory(file)
  const Icon = CATEGORY_ICONS[category as keyof typeof CATEGORY_ICONS] ?? CATEGORY_ICONS.Other
  const color = categoryColor(category)
  const reportKey = reportKeyOfFile(file)
  const { colorByKey } = useMemo(() => reportMaps(reports), [reports])
  const reportColor = colorByKey.get(reportKey) ?? "#64748b"
  const url = id ? evidenceUrl(id) : ""
  const thumbnailUrl = category === "Image" ? url : category === "Video" ? videoFrameUrl(id) : ""
  useEffect(() => {
    if (!thumbnailUrl || shouldLoadThumbnail) return

    const node = itemRef.current
    if (!node || typeof IntersectionObserver === "undefined") return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setShouldLoadThumbnail(true)
        observer.disconnect()
      },
      { rootMargin: "300px" }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [shouldLoadThumbnail, thumbnailUrl])

  const {
    objectUrl: protectedThumbnailUrl,
    error: thumbnailError,
  } = useProtectedObjectUrl(thumbnailUrl, Boolean(thumbnailUrl) && shouldLoadThumbnail && !imageFailed)
  const badges = fileBadges(file)
  const showPhoneChip = reports.length > 1 && reportKey
  const previewUrl = protectedThumbnailUrl ?? ""
  const previewFailed = imageFailed || Boolean(thumbnailError)

  if (layout === "list") {
    return (
      <button
        ref={itemRef}
        type="button"
        onClick={onOpen}
        className={cn(
          "flex w-full items-center gap-2 border-b border-border px-2 py-1.5 text-left transition-colors hover:bg-muted/60",
          selected && "bg-amber-500/10"
        )}
        style={showPhoneChip ? { borderLeft: `4px solid ${reportColor}` } : undefined}
      >
        <input
          type="checkbox"
          checked={selected}
          onChange={(event) => {
            event.stopPropagation()
            onToggleSelect(event.nativeEvent instanceof MouseEvent ? event.nativeEvent.shiftKey : false)
          }}
          onClick={(event) => event.stopPropagation()}
          className="size-3 shrink-0 accent-amber-500"
        />
        <PreviewBox thumbnailUrl={previewUrl} name={name} icon={Icon} color={color} imageFailed={previewFailed} onImageFailed={() => setImageFailed(true)} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-medium text-foreground">{name}</span>
          <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[10px] text-muted-foreground">
            <span>{category}</span>
            <span>-</span>
            <span>{fileSize(file) || "-"}</span>
            {fileParentLabel(file) ? (
              <>
                <span>-</span>
                <span className="truncate">{fileParentLabel(file)}</span>
              </>
            ) : null}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1">
          {showPhoneChip ? <PhoneReportChip reportKey={reportKey} reports={reports} className="max-w-32" /> : null}
          {file.is_relevant ? <CheckCircle2 className="size-3.5 text-emerald-500" /> : null}
          {fileTags(file).length ? <Tag className="size-3.5 text-amber-500" /> : null}
          {linkedEntityIds(file).length ? <User className="size-3.5 text-blue-500" /> : null}
        </span>
      </button>
    )
  }

  return (
    <button
      ref={itemRef}
      type="button"
      onClick={onOpen}
      title={name}
      className={cn(
        "group relative aspect-square overflow-hidden rounded-md border bg-muted/40 text-left transition-colors",
        selected ? "border-amber-500 ring-2 ring-amber-500/30" : "border-border hover:border-amber-500/60"
      )}
    >
      <div className="absolute inset-0 flex items-center justify-center bg-muted">
        {previewUrl && !previewFailed ? (
          <img src={previewUrl} alt={name} className="size-full object-cover" loading="lazy" onError={() => setImageFailed(true)} />
        ) : (
          <Icon className="size-8" style={{ color }} />
        )}
      </div>
      <label className="absolute left-1 top-1 rounded bg-background/90 px-1 py-0.5" onClick={(event) => event.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={(event) => onToggleSelect(event.nativeEvent instanceof MouseEvent ? event.nativeEvent.shiftKey : false)}
          className="size-3 accent-amber-500"
        />
      </label>
      {showPhoneChip ? (
        <span
          className="absolute left-1/2 top-1 max-w-20 -translate-x-1/2 truncate rounded-sm px-1 py-0.5 text-[10px] font-bold text-white shadow"
          style={{ backgroundColor: reportColor }}
          title={reportKey}
        >
          {readText(file, ["display_index"], reportKey).slice(0, 8)}
        </span>
      ) : null}
      <div className="absolute right-1 top-1 flex items-center gap-0.5">
        {badges.map((badge) => {
          if (!badge) return null
          const BadgeIcon = badge.icon
          return <BadgeIcon key={badge.key} className={cn("size-3.5 drop-shadow", badge.color)} />
        })}
      </div>
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-1.5 text-white">
        <div className="truncate text-[10px] font-medium">{name}</div>
        <div className="text-[9px] opacity-80">{fileSize(file)}</div>
      </div>
    </button>
  )
}

function PreviewBox({
  thumbnailUrl,
  name,
  icon: Icon,
  color,
  imageFailed,
  onImageFailed,
}: {
  thumbnailUrl: string
  name: string
  icon: LucideIcon
  color: string
  imageFailed: boolean
  onImageFailed: () => void
}) {
  return (
    <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded bg-muted">
      {thumbnailUrl && !imageFailed ? (
        <img src={thumbnailUrl} alt={name} className="size-full object-cover" loading="lazy" onError={onImageFailed} />
      ) : (
        <Icon className="size-4" style={{ color }} />
      )}
    </span>
  )
}
