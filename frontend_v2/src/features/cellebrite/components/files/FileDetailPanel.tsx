import { CheckCircle2, Download, ExternalLink, FileText, Pin, Sparkles, X } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { workspaceAPI } from "@/features/workspace/api"

import type { CellebriteRecord } from "../../types"
import { compactDate, readList, readText } from "../shared/cellebrite-format"
import {
  type CellebriteFileRecord,
  captureDate,
  categoryColor,
  evidenceUrl,
  fileCategory,
  fileId,
  fileName,
  fileSize,
  fileTags,
  linkedEntityIds,
} from "./filesUtils"
import type { EvidenceTagCount } from "./filesUtils"
import { FileEntityLinker } from "./FileEntityLinker"
import { FileTagEditor } from "./FileTagEditor"

export function FileDetailPanel({
  caseId,
  file,
  caseTags,
  onClose,
  onFileChanged,
}: {
  caseId: string
  file: CellebriteFileRecord | null
  caseTags: EvidenceTagCount[]
  onClose: () => void
  onFileChanged: (file: CellebriteFileRecord) => void
}) {
  if (!file) {
    return (
      <aside className="flex w-96 shrink-0 items-center justify-center border-l border-border bg-muted/20 p-4 text-center text-sm text-muted-foreground">
        Click a file to see details.
      </aside>
    )
  }

  const id = fileId(file)
  const category = fileCategory(file)
  const color = categoryColor(category)

  async function run(action: () => Promise<unknown>, success: string) {
    try {
      await action()
      toast.success(success)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Action failed")
    }
  }

  return (
    <aside className="flex w-96 shrink-0 flex-col border-l border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2" style={{ backgroundColor: `${color}18` }}>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground">{fileName(file)}</div>
          <div className="text-[11px] text-muted-foreground">
            {category} - {fileSize(file) || "unknown size"}
          </div>
        </div>
        <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} title="Close detail">
          <X className="size-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="border-b border-border p-3">
          <FilePreview file={file} />
        </div>
        <ParentBlock parent={file.parent} />
        <div className="border-b border-border px-3 py-2">
          <SectionLabel>Tags</SectionLabel>
          <FileTagEditor
            caseId={caseId}
            evidenceId={id}
            tags={fileTags(file)}
            caseTags={caseTags}
            onChange={(tags) => onFileChanged({ ...file, tags })}
          />
        </div>
        <div className="border-b border-border px-3 py-2">
          <SectionLabel>Linked entities</SectionLabel>
          <FileEntityLinker
            caseId={caseId}
            evidenceId={id}
            entityIds={linkedEntityIds(file)}
            onChange={(entityIds) => onFileChanged({ ...file, linked_entity_ids: entityIds })}
          />
        </div>
        <div className="border-b border-border px-3 py-2 text-[11px]">
          <SectionLabel>Metadata</SectionLabel>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1 text-muted-foreground">
            <dt>Category</dt>
            <dd className="text-foreground">{category}</dd>
            <dt>Size</dt>
            <dd className="text-foreground">{fileSize(file) || "-"}</dd>
            <dt>Status</dt>
            <dd className="text-foreground">{readText(file, ["status"], "-")}</dd>
            <dt>Captured</dt>
            <dd className="text-foreground">{compactDate(captureDate(file))}</dd>
            <dt>SHA256</dt>
            <dd className="break-all font-mono text-[10px] text-foreground">{readText(file, ["sha256"], "-")}</dd>
            <dt>Path</dt>
            <dd className="break-all text-foreground">
              {readList(file, ["device_path_segments"]).join("/") || readText(file, ["stored_path", "device_path"], "-")}
            </dd>
          </dl>
        </div>
        <div className="px-3 py-2">
          <SectionLabel>Actions</SectionLabel>
          <div className="grid grid-cols-2 gap-1.5">
            <ActionButton
              icon={CheckCircle2}
              label={file.is_relevant ? "Relevant" : "Mark relevant"}
              active={Boolean(file.is_relevant)}
              onClick={() =>
                void run(async () => {
                  await evidenceAPI.setRelevance([id], !file.is_relevant)
                  onFileChanged({ ...file, is_relevant: !file.is_relevant })
                }, file.is_relevant ? "Marked not relevant" : "Marked relevant")
              }
            />
            <ActionButton icon={Pin} label="Pin" onClick={() => void run(() => workspaceAPI.pinItem(caseId, "evidence", id), "Pinned file")} />
            <ActionButton icon={Sparkles} label="Process" onClick={() => void run(() => evidenceAPI.processBackground(caseId, [id]), "Started AI processing")} />
            <a
              href={evidenceUrl(id)}
              download={fileName(file)}
              className="inline-flex h-8 items-center justify-center gap-1 rounded-md border border-border px-2 text-xs hover:bg-muted"
            >
              <Download className="size-3.5" />
              Download
            </a>
          </div>
        </div>
      </div>
    </aside>
  )
}

function FilePreview({ file }: { file: CellebriteFileRecord }) {
  const id = fileId(file)
  const category = fileCategory(file)
  const url = evidenceUrl(id)

  if (category === "Image") {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="flex max-h-80 items-center justify-center overflow-hidden rounded-md border border-border bg-muted">
        <img src={url} alt={fileName(file)} className="max-h-80 w-full object-contain" />
      </a>
    )
  }
  if (category === "Audio") return <audio src={url} controls preload="metadata" className="w-full" />
  if (category === "Video") return <video src={url} controls preload="metadata" className="max-h-80 w-full bg-black" />
  if (category === "Text") {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-md border border-border px-2 py-2 text-xs hover:bg-muted">
        <FileText className="size-4 text-muted-foreground" />
        <span className="truncate">Open text preview</span>
      </a>
    )
  }
  return <div className="text-xs text-muted-foreground">No preview for this file type.</div>
}

function ParentBlock({ parent }: { parent?: CellebriteRecord | null }) {
  if (!parent) return null
  return (
    <div className="border-b border-border px-3 py-2 text-xs">
      <SectionLabel>Parent</SectionLabel>
      <div className="flex items-center gap-1 text-foreground">
        <ExternalLink className="size-3 text-muted-foreground" />
        <span className="font-medium">{readText(parent, ["label", "type"], "Parent")}</span>
        {readText(parent, ["source_app"]) ? <span className="text-muted-foreground">({readText(parent, ["source_app"])})</span> : null}
      </div>
      {readText(parent, ["name", "summary"]) ? (
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground">{readText(parent, ["name", "summary"])}</div>
      ) : null}
      {readText(parent, ["timestamp"]) ? <div className="mt-0.5 text-[10px] text-muted-foreground">{compactDate(parent.timestamp)}</div> : null}
    </div>
  )
}

function SectionLabel({ children }: { children: string }) {
  return <div className="mb-1 text-[11px] font-medium uppercase text-muted-foreground">{children}</div>
}

function ActionButton({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: typeof CheckCircle2
  label: string
  active?: boolean
  onClick: () => void
}) {
  return (
    <Button type="button" variant={active ? "secondary" : "outline"} size="sm" className="h-8 justify-start gap-1 px-2 text-xs" onClick={onClick}>
      <Icon className="size-3.5" />
      {label}
    </Button>
  )
}
