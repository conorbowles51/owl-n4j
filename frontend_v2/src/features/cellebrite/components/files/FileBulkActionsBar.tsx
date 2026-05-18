import { useRef, useState } from "react"
import { CheckCircle2, Pin, Sparkles, Tag, User, X } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { CaseProfilePicker } from "@/features/case-profiles/components/CaseProfilePicker"
import { evidenceAPI } from "@/features/evidence/api"
import { workspaceAPI } from "@/features/workspace/api"

import { evidenceTagsAPI } from "../../api"
import type { EvidenceTagCount } from "./filesUtils"

export function FileBulkActionsBar({
  caseId,
  selectedIds,
  caseTags,
  onClear,
  onChanged,
}: {
  caseId: string
  selectedIds: Set<string>
  caseTags: EvidenceTagCount[]
  onClear: () => void
  onChanged: () => void
}) {
  const [tagOpen, setTagOpen] = useState(false)
  const [entityOpen, setEntityOpen] = useState(false)
  const [tagInput, setTagInput] = useState("")
  const tagRef = useRef<HTMLDivElement | null>(null)
  const count = selectedIds.size
  const ids = [...selectedIds]

  if (count === 0) return null

  async function run(action: () => Promise<unknown>, success: string) {
    try {
      await action()
      toast.success(success)
      onChanged()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Action failed")
    }
  }

  async function addTag(tag: string) {
    const clean = tag.trim()
    if (!clean) return
    setTagInput("")
    setTagOpen(false)
    await run(() => evidenceTagsAPI.addTags(caseId, ids, [clean]), `Tagged ${count} file${count === 1 ? "" : "s"}`)
  }

  return (
    <div className="flex shrink-0 items-center gap-1 border-b border-border bg-amber-500/10 px-3 py-1.5 text-xs">
      <span className="mr-1 font-semibold text-amber-700 dark:text-amber-300">{count} selected</span>
      <div ref={tagRef} className="relative">
        <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setTagOpen((current) => !current)}>
          <Tag className="size-3" />
          Add tag
        </Button>
        {tagOpen ? (
          <div className="absolute left-0 top-8 z-30 w-64 rounded-md border border-border bg-popover p-2 shadow-lg">
            <Input
              autoFocus
              value={tagInput}
              onChange={(event) => setTagInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void addTag(tagInput)
                if (event.key === "Escape") setTagOpen(false)
              }}
              placeholder="New tag"
              className="h-8 text-xs"
            />
            {caseTags.length ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {caseTags.slice(0, 12).map((tag) => (
                  <button
                    key={tag.tag}
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault()
                      void addTag(tag.tag)
                    }}
                    className="rounded-full border border-amber-300 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-700 dark:text-amber-300"
                  >
                    {tag.tag} ({tag.count})
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="relative">
        <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setEntityOpen((current) => !current)}>
          <User className="size-3" />
          Link entity
        </Button>
        {entityOpen ? (
          <div className="absolute left-0 top-8 z-40 w-80">
            <CaseProfilePicker
              caseId={caseId}
              placeholder="Search case profiles..."
              onSelect={(profile) => {
                setEntityOpen(false)
                void run(
                  () => evidenceTagsAPI.linkEntities(caseId, ids, [profile.id]),
                  `Linked ${count} file${count === 1 ? "" : "s"} to ${profile.display_name}`
                )
              }}
            />
          </div>
        ) : null}
      </div>
      <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => void run(() => evidenceAPI.setRelevance(ids, true), "Marked files relevant")}>
        <CheckCircle2 className="size-3" />
        Mark relevant
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-xs"
        onClick={() =>
          void run(
            () => Promise.allSettled(ids.map((id) => workspaceAPI.pinItem(caseId, "evidence", id))),
            "Pinned selected files"
          )
        }
      >
        <Pin className="size-3" />
        Pin
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-xs"
        onClick={() => void run(() => evidenceAPI.processBackground(caseId, ids), "Started AI processing")}
      >
        <Sparkles className="size-3" />
        Process
      </Button>
      <div className="flex-1" />
      <Button type="button" variant="ghost" size="icon-sm" onClick={onClear} title="Clear selection">
        <X className="size-3.5" />
      </Button>
    </div>
  )
}
