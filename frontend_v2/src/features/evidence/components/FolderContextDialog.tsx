import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { InstructionListEditor } from "@/components/ui/instruction-list-editor"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { FolderOpen, Plus, Sparkles, X } from "lucide-react"
import { toast } from "sonner"
import {
  useEffectiveProfile,
  useFolderProfile,
  useUpdateFolderProfile,
} from "../hooks/use-folder-context"
import { ProfileChainPreview } from "./ProfileChainPreview"
import type { ProfileOverrides } from "@/types/evidence.types"

interface FolderContextDialogProps {
  folderId: string
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FolderContextDialog({
  folderId,
  caseId,
  open,
  onOpenChange,
}: FolderContextDialogProps) {
  const { data: profile, isLoading: profileLoading } =
    useFolderProfile(open ? folderId : null)
  const { data: effective, isLoading: effectiveLoading } =
    useEffectiveProfile(open ? folderId : null, caseId)
  const updateProfile = useUpdateFolderProfile(caseId)

  const [contextInstructions, setContextInstructions] = useState("")
  const [mandatoryInstructions, setMandatoryInstructions] = useState<string[]>([])
  const [entityTypes, setEntityTypes] = useState<
    { name: string; description: string }[]
  >([])
  const [newEntityName, setNewEntityName] = useState("")
  const [newEntityDesc, setNewEntityDesc] = useState("")

  useEffect(() => {
    if (!open) return

    setContextInstructions(profile?.context_instructions ?? "")
    setMandatoryInstructions(profile?.mandatory_instructions ?? [])
    setEntityTypes(
      (profile?.profile_overrides?.special_entity_types ?? []).map((entity) => ({
        name: entity.name,
        description: entity.description ?? "",
      }))
    )
    setNewEntityName("")
    setNewEntityDesc("")
  }, [open, profile])

  const addEntityType = useCallback(() => {
    const name = newEntityName.trim()
    if (!name) return

    if (entityTypes.some((entity) => entity.name.toLowerCase() === name.toLowerCase())) {
      toast.error("Entity type already exists")
      return
    }

    setEntityTypes((prev) => [
      ...prev,
      { name, description: newEntityDesc.trim() },
    ])
    setNewEntityName("")
    setNewEntityDesc("")
  }, [entityTypes, newEntityDesc, newEntityName])

  const removeEntityType = useCallback((index: number) => {
    setEntityTypes((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const handleSave = useCallback(() => {
    const overrides: ProfileOverrides = {}

    if (entityTypes.length > 0) {
      overrides.special_entity_types = entityTypes.map((entity) => ({
        name: entity.name,
        ...(entity.description ? { description: entity.description } : {}),
      }))
    }

    updateProfile.mutate(
      {
        folderId,
        context_instructions: contextInstructions.trim() || null,
        mandatory_instructions: mandatoryInstructions,
        profile_overrides:
          Object.keys(overrides).length > 0
            ? (overrides as Record<string, unknown>)
            : null,
      },
      {
        onSuccess: () => {
          toast.success("Folder profile saved")
          onOpenChange(false)
        },
        onError: (error) => {
          toast.error(error.message || "Failed to save folder profile")
        },
      }
    )
  }, [contextInstructions, entityTypes, folderId, mandatoryInstructions, onOpenChange, updateProfile])

  const isLoading = profileLoading || effectiveLoading
  const previewOverrides = useMemo<ProfileOverrides | null>(() => {
    if (entityTypes.length === 0) {
      return null
    }

    return {
      special_entity_types: entityTypes.map((entity) => ({
        name: entity.name,
        ...(entity.description ? { description: entity.description } : {}),
      })),
    }
  }, [entityTypes])

  const previewChain = useMemo(() => {
    if (!effective) {
      return []
    }

    return effective.chain.map((link) => {
      if (link.folder_id !== folderId) {
        return link
      }

      return {
        ...link,
        context_instructions: contextInstructions.trim() || null,
        mandatory_instructions: mandatoryInstructions,
        profile_overrides: previewOverrides,
      }
    })
  }, [contextInstructions, effective, folderId, mandatoryInstructions, previewOverrides])

  const previewEffectiveContext = useMemo(() => {
    return previewChain
      .map((link) => {
        if (!link.context_instructions?.trim()) {
          return null
        }
        return `[${link.folder_name}]\n${link.context_instructions.trim()}`
      })
      .filter(Boolean)
      .join("\n\n")
  }, [previewChain])

  const previewEffectiveEntityTypes = useMemo(() => {
    const merged = new Map<string, { name: string; description?: string | null }>()

    for (const link of previewChain) {
      for (const entity of link.profile_overrides?.special_entity_types ?? []) {
        merged.set(entity.name.toLowerCase(), entity)
      }
    }

    return Array.from(merged.values())
  }, [previewChain])

  const previewEffectiveInstructions = useMemo(() => {
    const seen = new Set<string>()
    const merged: string[] = []

    for (const instruction of previewChain.flatMap((link) => link.mandatory_instructions ?? [])) {
      const normalized = instruction.trim().toLowerCase()
      if (!normalized || seen.has(normalized)) {
        continue
      }
      seen.add(normalized)
      merged.push(instruction)
    }

    return merged
  }, [previewChain])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[92vw] flex-col overflow-hidden sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderOpen className="size-4 text-amber-500" />
            Folder Processing Profile
          </DialogTitle>
          <DialogDescription>
            Add folder-specific extraction instructions. Files inherit the case
            base profile plus every folder layer above them.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : (
          <ScrollArea className="flex-1 -mx-6 px-6">
            <div className="space-y-5 py-1">
              <div className="space-y-1.5">
                <Label htmlFor="folder-context-textarea">Folder Context</Label>
                <Textarea
                  id="folder-context-textarea"
                  value={contextInstructions}
                  onChange={(event) => setContextInstructions(event.target.value)}
                  placeholder="Describe what kinds of documents are in this folder and any useful background..."
                  className="min-h-[140px] text-sm"
                />
                <p className="text-[10px] text-muted-foreground">
                  This background context is appended after the case base profile and
                  any ancestor folder context.
                </p>
              </div>

              <InstructionListEditor
                label="Folder Mandatory Instructions"
                description="Add one-line extraction rules for this folder. Rules are applied in order from the case down into deeper folders, so later rules are more specific and take priority."
                instructions={mandatoryInstructions}
                onChange={setMandatoryInstructions}
                placeholder="Ignore opening-balance and balance-forward rows."
                badgeVariant="amber"
              />

              <div className="space-y-2 rounded-lg border border-border p-4">
                <div className="space-y-1">
                  <Label>
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="size-3 text-amber-500" />
                      Special Entity Types
                    </span>
                  </Label>
                  <p className="text-[10px] text-muted-foreground">
                    Add structured entity types this folder should emphasize.
                    Child folders can replace matching types by name.
                  </p>
                </div>

                {entityTypes.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {entityTypes.map((entity, index) => (
                      <Badge key={`${entity.name}-${index}`} variant="amber" className="gap-1 pr-1">
                        <span>{entity.name}</span>
                        {entity.description ? (
                          <span className="text-amber-500/70" title={entity.description}>
                            *
                          </span>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeEntityType(index)}
                          className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-amber-500/20"
                          aria-label={`Remove ${entity.name}`}
                        >
                          <X className="size-2.5" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No folder-local entity hints set.
                  </p>
                )}

                <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                  <Input
                    value={newEntityName}
                    onChange={(event) => setNewEntityName(event.target.value)}
                    placeholder="Entity type name"
                    className="h-8 text-xs"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault()
                        addEntityType()
                      }
                    }}
                  />
                  <Input
                    value={newEntityDesc}
                    onChange={(event) => setNewEntityDesc(event.target.value)}
                    placeholder="Description (optional)"
                    className="h-8 text-xs"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault()
                        addEntityType()
                      }
                    }}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={addEntityType}
                    disabled={!newEntityName.trim()}
                  >
                    <Plus className="size-3.5" />
                    Add
                  </Button>
                </div>
              </div>

              {effective ? (
                <div className="space-y-4 rounded-lg border border-border p-4">
                  <ProfileChainPreview chain={previewChain} />

                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground">
                      Effective Context Preview
                    </p>
                    <div className="rounded-md bg-slate-50 p-3 dark:bg-slate-900/50">
                      {previewEffectiveContext ? (
                        <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground">
                          {previewEffectiveContext}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          No inherited or local instructions set yet.
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground">
                      Effective Mandatory Rules
                    </p>
                    {previewEffectiveInstructions.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {previewEffectiveInstructions.map((instruction, index) => (
                          <Badge key={`${instruction}-${index}`} variant="amber" className="text-[10px]">
                            {instruction}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        No effective mandatory rules.
                      </p>
                    )}
                  </div>

                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground">
                      Effective Special Entity Types
                    </p>
                    {previewEffectiveEntityTypes.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {previewEffectiveEntityTypes.map((entity) => (
                          <Badge key={entity.name} variant="secondary" className="text-[10px]">
                            {entity.name}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        No effective entity-type hints.
                      </p>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </ScrollArea>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={updateProfile.isPending || isLoading}
          >
            {updateProfile.isPending ? "Saving..." : "Save Folder Profile"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
