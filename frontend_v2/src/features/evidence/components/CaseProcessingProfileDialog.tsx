import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { InstructionListEditor } from "@/components/ui/instruction-list-editor"
import { BriefcaseBusiness, Plus, X } from "lucide-react"
import { toast } from "sonner"
import { profilesAPI } from "@/features/admin/api"
import type { CaseProcessingProfile } from "@/types/evidence.types"
import {
  useCaseProcessingProfile,
  useUpdateCaseProcessingProfile,
} from "../hooks/use-case-processing-profile"

interface CaseProcessingProfileDialogProps {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

const NONE_PROFILE_VALUE = "__none__"

interface EntityTypeDraft {
  name: string
  description: string
}

interface CaseProfileDraft {
  sourceKey: string
  selectedProfileName: string
  contextInstructions: string
  mandatoryInstructions: string[]
  entityTypes: EntityTypeDraft[]
  newEntityName: string
  newEntityDesc: string
}

function toEntityTypeDrafts(
  entities: { name: string; description?: string | null }[] = []
): EntityTypeDraft[] {
  return entities.map((entity) => ({
    name: entity.name,
    description: entity.description ?? "",
  }))
}

function createCaseProfileDraft(
  caseProfile: CaseProcessingProfile | undefined
): CaseProfileDraft {
  return {
    sourceKey: JSON.stringify([
      caseProfile?.source_profile_name ?? NONE_PROFILE_VALUE,
      caseProfile?.context_instructions ?? "",
      caseProfile?.mandatory_instructions ?? [],
      caseProfile?.special_entity_types ?? [],
    ]),
    selectedProfileName: caseProfile?.source_profile_name ?? NONE_PROFILE_VALUE,
    contextInstructions: caseProfile?.context_instructions ?? "",
    mandatoryInstructions: caseProfile?.mandatory_instructions ?? [],
    entityTypes: toEntityTypeDrafts(caseProfile?.special_entity_types),
    newEntityName: "",
    newEntityDesc: "",
  }
}

export function CaseProcessingProfileDialog({
  caseId,
  open,
  onOpenChange,
}: CaseProcessingProfileDialogProps) {
  const { data: libraryProfiles = [], isLoading: libraryLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn: () => profilesAPI.list(),
    enabled: open,
  })
  const { data: caseProfile, isLoading: caseLoading } = useCaseProcessingProfile(caseId, open)
  const updateCaseProfile = useUpdateCaseProcessingProfile(caseId)

  const sourceDraft = useMemo(
    () => createCaseProfileDraft(caseProfile),
    [caseProfile]
  )
  const [draft, setDraft] = useState(sourceDraft)
  const activeDraft =
    draft.sourceKey === sourceDraft.sourceKey ? draft : sourceDraft
  const {
    selectedProfileName,
    contextInstructions,
    mandatoryInstructions,
    entityTypes,
    newEntityName,
    newEntityDesc,
  } = activeDraft
  const updateDraft = (updates: Partial<Omit<CaseProfileDraft, "sourceKey">>) => {
    setDraft((current) => ({
      ...(current.sourceKey === sourceDraft.sourceKey ? current : sourceDraft),
      ...updates,
    }))
  }

  const setContextInstructions = (contextInstructions: string) =>
    updateDraft({ contextInstructions })
  const setMandatoryInstructions = (mandatoryInstructions: string[]) =>
    updateDraft({ mandatoryInstructions })
  const setNewEntityName = (newEntityName: string) =>
    updateDraft({ newEntityName })
  const setNewEntityDesc = (newEntityDesc: string) =>
    updateDraft({ newEntityDesc })

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setDraft(sourceDraft)
    }
    onOpenChange(nextOpen)
  }

  const selectedLibraryProfile = useMemo(
    () =>
      libraryProfiles.find((profile) => profile.name === selectedProfileName) ?? null,
    [libraryProfiles, selectedProfileName]
  )

  const handleLibraryProfileChange = (value: string) => {
    if (value === NONE_PROFILE_VALUE) {
      updateDraft({ selectedProfileName: value })
      return
    }

    const profile = libraryProfiles.find((item) => item.name === value)
    if (!profile) return

    updateDraft({
      selectedProfileName: value,
      contextInstructions: profile.context_instructions ?? "",
      mandatoryInstructions: profile.mandatory_instructions ?? [],
      entityTypes: toEntityTypeDrafts(profile.special_entity_types),
    })
  }

  const addEntityType = () => {
    const name = newEntityName.trim()
    if (!name) return

    if (entityTypes.some((entity) => entity.name.toLowerCase() === name.toLowerCase())) {
      toast.error("Entity type already exists")
      return
    }

    updateDraft({
      entityTypes: [
        ...entityTypes,
        { name, description: newEntityDesc.trim() },
      ],
      newEntityName: "",
      newEntityDesc: "",
    })
  }

  const removeEntityType = (index: number) => {
    updateDraft({ entityTypes: entityTypes.filter((_, i) => i !== index) })
  }

  const handleSave = () => {
    updateCaseProfile.mutate(
      {
        source_profile_name:
          selectedProfileName === NONE_PROFILE_VALUE ? null : selectedProfileName,
        context_instructions: contextInstructions.trim() || null,
        mandatory_instructions: mandatoryInstructions,
        special_entity_types: entityTypes.map((entity) => ({
          name: entity.name,
          ...(entity.description ? { description: entity.description } : {}),
        })),
      },
      {
        onSuccess: () => {
          toast.success("Case processing profile saved")
          handleOpenChange(false)
        },
        onError: (error) => {
          toast.error(error.message || "Failed to save case processing profile")
        },
      }
    )
  }

  const isLoading = libraryLoading || caseLoading

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[92vw] flex-col overflow-hidden sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BriefcaseBusiness className="size-4 text-amber-500" />
            Case Processing Profile
          </DialogTitle>
          <DialogDescription>
            Set the base profile that every evidence file in this case inherits
            before folder-specific instructions are applied.
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
                <Label htmlFor="case-library-profile">Library Profile</Label>
                <Select value={selectedProfileName} onValueChange={handleLibraryProfileChange}>
                  <SelectTrigger id="case-library-profile" className="w-full">
                    <SelectValue placeholder="Choose a reusable profile" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE_PROFILE_VALUE}>No library profile</SelectItem>
                    {selectedProfileName !== NONE_PROFILE_VALUE && !selectedLibraryProfile ? (
                      <SelectItem value={selectedProfileName}>
                        {selectedProfileName} (missing)
                      </SelectItem>
                    ) : null}
                    {libraryProfiles.map((profile) => (
                      <SelectItem key={profile.name} value={profile.name}>
                        {profile.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedLibraryProfile?.description ? (
                  <p className="text-[10px] text-muted-foreground">
                    {selectedLibraryProfile.description}
                  </p>
                ) : null}
                {caseProfile?.source_profile_name && !caseProfile.source_profile_exists ? (
                  <p className="text-[10px] text-amber-600 dark:text-amber-400">
                    This case references a profile name that no longer exists in
                    the shared library. The saved case snapshot is still editable.
                  </p>
                ) : null}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="case-context-textarea">Base Context</Label>
                <Textarea
                  id="case-context-textarea"
                  value={contextInstructions}
                  onChange={(event) => setContextInstructions(event.target.value)}
                  placeholder="Describe the overall document context for this case..."
                  className="min-h-[160px] text-sm"
                />
                <p className="text-[10px] text-muted-foreground">
                  Choosing a library profile copies its current instructions into
                  this case. Further edits here stay case-specific.
                </p>
              </div>

              <InstructionListEditor
                label="Base Mandatory Instructions"
                description="Add one-line extraction rules that should be treated as mandatory for every file in this case. Folder rules added later can become more specific and take priority."
                instructions={mandatoryInstructions}
                onChange={setMandatoryInstructions}
                placeholder="Extract every transaction as a separate financial event."
                badgeVariant="info"
              />

              <div className="space-y-2 rounded-lg border border-border p-4">
                <div className="space-y-1">
                  <Label>Base Special Entity Types</Label>
                  <p className="text-[10px] text-muted-foreground">
                    These structured hints apply across the whole case unless a
                    deeper folder replaces a matching entity type by name.
                  </p>
                </div>

                {entityTypes.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {entityTypes.map((entity, index) => (
                      <Badge key={`${entity.name}-${index}`} variant="secondary" className="gap-1 pr-1">
                        <span>{entity.name}</span>
                        {entity.description ? (
                          <span className="text-muted-foreground" title={entity.description}>
                            *
                          </span>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeEntityType(index)}
                          className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-muted"
                          aria-label={`Remove ${entity.name}`}
                        >
                          <X className="size-2.5" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No case-wide entity hints set.
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

              <div className="space-y-3 rounded-lg border border-border p-4">
                <p className="text-xs font-medium text-muted-foreground">
                  Base Profile Preview
                </p>
                <div className="rounded-md bg-slate-50 p-3 dark:bg-slate-900/50">
                  {contextInstructions.trim() ? (
                    <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground">
                      {contextInstructions}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No case base instructions set.
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">
                    Effective Mandatory Rules
                  </p>
                  {mandatoryInstructions.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {mandatoryInstructions.map((instruction, index) => (
                        <Badge key={`${instruction}-${index}`} variant="info" className="text-[10px]">
                          {instruction}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No case-wide mandatory rules.
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {entityTypes.length > 0 ? (
                    entityTypes.map((entity) => (
                      <Badge key={entity.name} variant="secondary" className="text-[10px]">
                        {entity.name}
                      </Badge>
                    ))
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No case-wide entity types.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </ScrollArea>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={updateCaseProfile.isPending || isLoading}
          >
            {updateCaseProfile.isPending ? "Saving..." : "Save Case Profile"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
