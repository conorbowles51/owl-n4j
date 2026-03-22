import { useState, useEffect, useCallback } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Slider } from "@/components/ui/slider"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"
import {
  FolderOpen,
  ChevronDown,
  ChevronUp,
  Plus,
  X,
  Settings2,
  Sparkles,
} from "lucide-react"
import { toast } from "sonner"
import {
  useFolderProfile,
  useEffectiveProfile,
  useUpdateFolderProfile,
} from "../hooks/use-folder-context"
import { ProfileChainPreview } from "./ProfileChainPreview"
import type { ProfileOverrides, ProfileTemplate } from "@/types/evidence.types"

/* ------------------------------------------------------------------ */
/*  Built-in templates                                                */
/* ------------------------------------------------------------------ */

const BUILT_IN_TEMPLATES: ProfileTemplate[] = [
  {
    id: "generic",
    name: "Generic",
    description: "No specific context. Files processed with default settings.",
    context_instructions: "",
  },
  {
    id: "financial",
    name: "Financial Records",
    description:
      "Bank statements, transaction records, and account statements.",
    context_instructions:
      "This folder contains financial documents including bank statements, transaction records, and account statements. Focus on extracting transaction amounts, dates, account numbers, counterparties, and financial patterns.",
  },
  {
    id: "wiretap",
    name: "Wiretap / Communications",
    description:
      "Communication recordings and their associated metadata files.",
    context_instructions:
      "This folder contains communication recordings and their associated metadata files. Each subfolder may contain an audio recording and related metadata. Link participants mentioned in metadata as parties to communication events.",
  },
  {
    id: "legal",
    name: "Legal Documents",
    description: "Contracts, court filings, and legal correspondence.",
    context_instructions:
      "This folder contains legal documents including contracts, court filings, and legal correspondence. Extract parties, dates, obligations, case references, and legal terms.",
  },
  {
    id: "correspondence",
    name: "Correspondence",
    description: "Emails, letters, and messages.",
    context_instructions:
      "This folder contains emails, letters, and messages. Extract senders, recipients, dates, subjects, and key topics discussed.",
  },
]

/* ------------------------------------------------------------------ */
/*  Props                                                             */
/* ------------------------------------------------------------------ */

interface FolderContextDialogProps {
  folderId: string
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function FolderContextDialog({
  folderId,
  caseId,
  open,
  onOpenChange,
}: FolderContextDialogProps) {
  /* ---- queries ---- */
  const { data: profile, isLoading: profileLoading } =
    useFolderProfile(open ? folderId : null)
  const { data: effective, isLoading: effectiveLoading } =
    useEffectiveProfile(open ? folderId : null, caseId)
  const updateProfile = useUpdateFolderProfile(caseId)

  /* ---- local state ---- */
  const [contextInstructions, setContextInstructions] = useState("")
  const [selectedTemplate, setSelectedTemplate] = useState("generic")
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [entityTypes, setEntityTypes] = useState<
    { name: string; description: string }[]
  >([])
  const [temperature, setTemperature] = useState(0.3)
  const [newEntityName, setNewEntityName] = useState("")
  const [newEntityDesc, setNewEntityDesc] = useState("")

  /* ---- seed form from fetched profile ---- */
  useEffect(() => {
    if (!open) return
    if (profile) {
      setContextInstructions(profile.context_instructions ?? "")
      setEntityTypes(
        (profile.profile_overrides?.special_entity_types ?? []).map((e) => ({
          name: e.name,
          description: e.description ?? "",
        }))
      )
      setTemperature(profile.profile_overrides?.temperature ?? 0.3)

      // Detect if current instructions match a template
      const match = BUILT_IN_TEMPLATES.find(
        (t) => t.context_instructions === (profile.context_instructions ?? "")
      )
      setSelectedTemplate(match?.id ?? "generic")
    } else {
      // Reset for new / empty profile
      setContextInstructions("")
      setSelectedTemplate("generic")
      setEntityTypes([])
      setTemperature(0.3)
    }
    setAdvancedOpen(false)
    setNewEntityName("")
    setNewEntityDesc("")
  }, [open, profile])

  /* ---- template selection ---- */
  const handleTemplateChange = useCallback((templateId: string) => {
    setSelectedTemplate(templateId)
    const tmpl = BUILT_IN_TEMPLATES.find((t) => t.id === templateId)
    if (tmpl) {
      setContextInstructions(tmpl.context_instructions)
    }
  }, [])

  /* ---- entity type helpers ---- */
  const addEntityType = useCallback(() => {
    const name = newEntityName.trim()
    if (!name) return
    if (entityTypes.some((e) => e.name.toLowerCase() === name.toLowerCase())) {
      toast.error("Entity type already exists")
      return
    }
    setEntityTypes((prev) => [
      ...prev,
      { name, description: newEntityDesc.trim() },
    ])
    setNewEntityName("")
    setNewEntityDesc("")
  }, [newEntityName, newEntityDesc, entityTypes])

  const removeEntityType = useCallback((index: number) => {
    setEntityTypes((prev) => prev.filter((_, i) => i !== index))
  }, [])

  /* ---- save ---- */
  const handleSave = useCallback(() => {
    const overrides: ProfileOverrides = {}
    if (entityTypes.length > 0) {
      overrides.special_entity_types = entityTypes.map((e) => ({
        name: e.name,
        ...(e.description ? { description: e.description } : {}),
      }))
    }
    if (temperature !== 0.3) {
      overrides.temperature = temperature
    }

    const hasOverrides = Object.keys(overrides).length > 0

    updateProfile.mutate(
      {
        folderId,
        context_instructions: contextInstructions || null,
        profile_overrides: hasOverrides ? overrides : null,
      },
      {
        onSuccess: () => {
          toast.success("Folder profile saved")
          onOpenChange(false)
        },
        onError: () => {
          toast.error("Failed to save folder profile")
        },
      }
    )
  }, [
    folderId,
    contextInstructions,
    entityTypes,
    temperature,
    updateProfile,
    onOpenChange,
  ])

  /* ---- loading state ---- */
  const isLoading = profileLoading || effectiveLoading

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderOpen className="size-4 text-amber-500" />
            Folder Context &amp; Profile
          </DialogTitle>
          <DialogDescription>
            Set processing instructions for this folder. Sub-folders inherit
            parent context and can add their own.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : (
          <ScrollArea className="flex-1 -mx-6 px-6">
            <div className="space-y-5 py-1">
              {/* ---- Template selector ---- */}
              <div className="space-y-1.5">
                <Label htmlFor="template-select">Template</Label>
                <Select
                  value={selectedTemplate}
                  onValueChange={handleTemplateChange}
                >
                  <SelectTrigger id="template-select" className="w-full">
                    <SelectValue placeholder="Choose a template..." />
                  </SelectTrigger>
                  <SelectContent>
                    {BUILT_IN_TEMPLATES.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        <span className="font-medium">{t.name}</span>
                        <span className="ml-1.5 text-muted-foreground">
                          — {t.description}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* ---- Context instructions ---- */}
              <div className="space-y-1.5">
                <Label htmlFor="context-textarea">Context Instructions</Label>
                <Textarea
                  id="context-textarea"
                  value={contextInstructions}
                  onChange={(e) => {
                    setContextInstructions(e.target.value)
                    // If user edits, deselect template match
                    const match = BUILT_IN_TEMPLATES.find(
                      (t) => t.context_instructions === e.target.value
                    )
                    setSelectedTemplate(match?.id ?? "generic")
                  }}
                  placeholder="Describe how files in this folder should be analyzed..."
                  className="min-h-[120px] text-sm"
                />
                <p className="text-[10px] text-muted-foreground">
                  These instructions are prepended to the LLM prompt during
                  entity extraction.
                </p>
              </div>

              {/* ---- Advanced settings (collapsible) ---- */}
              <div className="rounded-lg border border-border">
                <button
                  type="button"
                  onClick={() => setAdvancedOpen((v) => !v)}
                  className={cn(
                    "flex w-full items-center justify-between px-3.5 py-2.5 text-left text-sm font-medium transition-colors hover:bg-muted/50",
                    advancedOpen && "border-b border-border"
                  )}
                >
                  <span className="flex items-center gap-2">
                    <Settings2 className="size-3.5 text-muted-foreground" />
                    Advanced Settings
                  </span>
                  {advancedOpen ? (
                    <ChevronUp className="size-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="size-4 text-muted-foreground" />
                  )}
                </button>

                {advancedOpen && (
                  <div className="space-y-5 p-3.5">
                    {/* Special entity types */}
                    <div className="space-y-2">
                      <Label>
                        <span className="flex items-center gap-1.5">
                          <Sparkles className="size-3 text-amber-500" />
                          Special Entity Types
                        </span>
                      </Label>
                      <p className="text-[10px] text-muted-foreground">
                        Define custom entity types the LLM should look for in
                        addition to standard entities.
                      </p>

                      {/* Existing entity types */}
                      {entityTypes.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {entityTypes.map((entity, idx) => (
                            <Badge
                              key={idx}
                              variant="amber"
                              className="gap-1 pr-1"
                            >
                              <span>{entity.name}</span>
                              {entity.description && (
                                <span
                                  className="text-amber-500/60"
                                  title={entity.description}
                                >
                                  *
                                </span>
                              )}
                              <button
                                type="button"
                                onClick={() => removeEntityType(idx)}
                                className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-amber-500/20"
                                aria-label={`Remove ${entity.name}`}
                              >
                                <X className="size-2.5" />
                              </button>
                            </Badge>
                          ))}
                        </div>
                      )}

                      {/* Add new entity type */}
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <Input
                            value={newEntityName}
                            onChange={(e) => setNewEntityName(e.target.value)}
                            placeholder="Entity type name"
                            className="h-7 text-xs"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault()
                                addEntityType()
                              }
                            }}
                          />
                        </div>
                        <div className="flex-1">
                          <Input
                            value={newEntityDesc}
                            onChange={(e) => setNewEntityDesc(e.target.value)}
                            placeholder="Description (optional)"
                            className="h-7 text-xs"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault()
                                addEntityType()
                              }
                            }}
                          />
                        </div>
                        <Button
                          variant="outline"
                          size="icon-sm"
                          onClick={addEntityType}
                          disabled={!newEntityName.trim()}
                          aria-label="Add entity type"
                        >
                          <Plus className="size-3.5" />
                        </Button>
                      </div>
                    </div>

                    {/* Temperature slider */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="temperature-slider">Temperature</Label>
                        <span className="text-xs font-mono tabular-nums text-muted-foreground">
                          {temperature.toFixed(1)}
                        </span>
                      </div>
                      <Slider
                        id="temperature-slider"
                        value={[temperature]}
                        onValueChange={([v]) => setTemperature(v)}
                        min={0}
                        max={1}
                        step={0.1}
                      />
                      <div className="flex justify-between text-[10px] text-muted-foreground">
                        <span>Precise (0.0)</span>
                        <span>Creative (1.0)</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* ---- Profile chain preview ---- */}
              {effective && effective.chain.length > 0 && (
                <div className="rounded-lg border border-border p-3.5">
                  <ProfileChainPreview chain={effective.chain} />
                  {effective.merged_context && (
                    <div className="mt-3 space-y-1.5">
                      <p className="text-[10px] font-medium text-muted-foreground">
                        Merged Context (all ancestors)
                      </p>
                      <div className="rounded-md bg-slate-50 p-2.5 dark:bg-slate-900/50">
                        <p className="text-xs leading-relaxed text-muted-foreground line-clamp-4">
                          {effective.merged_context}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}
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
            {updateProfile.isPending ? "Saving..." : "Save Profile"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
