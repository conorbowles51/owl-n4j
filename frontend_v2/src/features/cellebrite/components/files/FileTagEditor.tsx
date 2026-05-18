import { useRef, useState } from "react"
import { Plus, Tag, X } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import { evidenceTagsAPI } from "../../api"
import type { EvidenceTagCount } from "./filesUtils"

export function FileTagEditor({
  caseId,
  evidenceId,
  tags,
  caseTags,
  onChange,
}: {
  caseId: string
  evidenceId: string
  tags: string[]
  caseTags: EvidenceTagCount[]
  onChange: (tags: string[]) => void
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [editing, setEditing] = useState(false)
  const [input, setInput] = useState("")
  const [saving, setSaving] = useState(false)
  const suggestions = caseTags
    .filter((tag) => !tags.includes(tag.tag))
    .filter((tag) => !input || tag.tag.toLowerCase().includes(input.toLowerCase()))
    .slice(0, 6)

  async function commit(nextTags: string[]) {
    setSaving(true)
    try {
      await evidenceTagsAPI.setTags(caseId, evidenceId, nextTags)
      onChange(nextTags)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update tags")
    } finally {
      setSaving(false)
    }
  }

  async function addTag(raw: string) {
    const tag = raw.trim()
    if (!tag || tags.includes(tag)) return
    setInput("")
    setEditing(false)
    await commit([...tags, tag].sort())
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-700 dark:text-amber-300"
        >
          <Tag className="size-2.5" />
          {tag}
          <button type="button" onClick={() => void commit(tags.filter((item) => item !== tag))} title={`Remove ${tag}`}>
            <X className="size-2.5" />
          </button>
        </span>
      ))}
      {editing ? (
        <span className="relative">
          <Input
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                void addTag(input)
              }
              if (event.key === "Escape") {
                setEditing(false)
                setInput("")
              }
            }}
            onBlur={() => window.setTimeout(() => setEditing(false), 150)}
            placeholder="Add tag"
            className="h-7 w-32 text-xs"
            disabled={saving}
          />
          {suggestions.length > 0 ? (
            <div className="absolute left-0 top-8 z-30 min-w-36 rounded-md border border-border bg-popover p-1 shadow-lg">
              {suggestions.map((tag) => (
                <button
                  key={tag.tag}
                  type="button"
                  onMouseDown={(event) => {
                    event.preventDefault()
                    void addTag(tag.tag)
                  }}
                  className="block w-full rounded px-2 py-1 text-left text-[11px] hover:bg-muted"
                >
                  {tag.tag} <span className="text-muted-foreground">({tag.count})</span>
                </button>
              ))}
            </div>
          ) : null}
        </span>
      ) : (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-1.5 text-[11px]"
          onClick={() => {
            setEditing(true)
            window.setTimeout(() => inputRef.current?.focus(), 0)
          }}
        >
          <Plus className="size-3" />
          tag
        </Button>
      )}
    </div>
  )
}
