import { useEffect, useState } from "react"
import { GitBranch, Link2Off, Plus, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Textarea } from "@/components/ui/textarea"
import { NotebookEntityPicker } from "@/features/notebook/components/NotebookEntityPicker"
import { cn } from "@/lib/cn"
import { useCreateDossier } from "../hooks"

const TYPES = [
  "person",
  "organisation",
  "device",
  "vehicle",
  "address",
  "event",
  "other",
]
const BUILTIN_ROLES = [
  "Subject",
  "Witness",
  "Source",
  "Complainant",
  "Affected Party",
  "Expert",
  "Client",
  "Key Contact",
  "Custodian",
]

export function DossierCreateSheet({
  caseId,
  open,
  onOpenChange,
  initialEntity,
}: {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  initialEntity?: { key: string; name?: string } | null
}) {
  const [mode, setMode] = useState<"linked" | "unlinked">(
    initialEntity ? "linked" : "unlinked"
  )
  const [entity, setEntity] = useState(initialEntity ?? null)
  const [name, setName] = useState(initialEntity?.name ?? "")
  const [type, setType] = useState("person")
  const [summary, setSummary] = useState("")
  const [importance, setImportance] = useState("")
  const [roles, setRoles] = useState<string[]>([])
  const [customRole, setCustomRole] = useState("")
  const create = useCreateDossier(caseId)
  useEffect(() => {
    if (!open) {
      setMode(initialEntity ? "linked" : "unlinked")
      setEntity(initialEntity ?? null)
      setName(initialEntity?.name ?? "")
      setType("person")
      setSummary("")
      setImportance("")
      setRoles([])
      setCustomRole("")
    }
  }, [initialEntity, open])
  const canSave =
    mode === "linked" ? Boolean(entity?.key) : Boolean(name.trim())

  const save = async () => {
    try {
      await create.mutateAsync({
        dossier_type: type,
        display_name: name.trim() || entity?.name,
        canonical_entity_key: mode === "linked" ? entity?.key : null,
        summary: summary.trim() || null,
        importance: importance.trim() || null,
        roles: roles.map((role) => ({ name: role })),
      })
      toast.success("Dossier created")
      onOpenChange(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not create Dossier"
      )
    }
  }

  const toggleRole = (role: string) =>
    setRoles((current) =>
      current.includes(role)
        ? current.filter((item) => item !== role)
        : [...current, role]
    )
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-xl">
        <SheetHeader className="border-b border-border px-5 py-4">
          <SheetTitle>New Dossier</SheetTitle>
          <SheetDescription>
            Curate casework around a graph subject, or begin with an unlinked
            subject and connect it later.
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-5 p-5">
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/50 p-1">
            {(["linked", "unlinked"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={cn(
                  "flex h-9 items-center justify-center gap-2 rounded-md text-xs font-medium transition",
                  mode === value
                    ? "bg-background text-foreground shadow-sm ring-1 ring-border"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {value === "linked" ? (
                  <GitBranch className="size-3.5" />
                ) : (
                  <Link2Off className="size-3.5" />
                )}
                {value === "linked" ? "From graph entity" : "Unlinked subject"}
              </button>
            ))}
          </div>
          {mode === "linked" ? (
            <div className="space-y-2">
              <Label>Canonical graph entity</Label>
              {entity ? (
                <div className="flex items-center gap-3 rounded-lg border border-brand-300/60 bg-brand-50/40 p-3 dark:bg-brand-500/10">
                  <GitBranch className="size-4 text-brand-600" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {entity.name || entity.key}
                    </p>
                    <p className="truncate font-mono text-[10px] text-muted-foreground">
                      {entity.key}
                    </p>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Clear selected entity"
                    onClick={() => setEntity(null)}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ) : (
                <NotebookEntityPicker
                  caseId={caseId}
                  onAttach={(link) =>
                    setEntity({
                      key: link.target_id,
                      name: link.target_label ?? undefined,
                    })
                  }
                />
              )}
              <p className="text-[11px] text-muted-foreground">
                Identity facts stay current from the graph. Creating this
                Dossier also adds the entity to Significant.
              </p>
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="dossier-name">Working display name</Label>
              <Input
                id="dossier-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Unknown caller, Company X…"
              />
              <p className="text-[11px] text-muted-foreground">
                Clearly shown as unlinked until connected to a graph entity.
              </p>
            </div>
          )}
          <div className="grid gap-2">
            <Label>Subject type</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item[0].toUpperCase() + item.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dossier-importance">Why this subject matters</Label>
            <Input
              id="dossier-importance"
              value={importance}
              onChange={(event) => setImportance(event.target.value)}
              placeholder="Central subject, key source, controlling device…"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dossier-summary">Investigator summary</Label>
            <Textarea
              id="dossier-summary"
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              rows={5}
              placeholder="Current relevance, open questions, and strategic context…"
            />
          </div>
          <div className="space-y-2">
            <Label>Case-specific roles</Label>
            <div className="flex flex-wrap gap-1.5">
              {BUILTIN_ROLES.map((role) => (
                <button
                  type="button"
                  key={role}
                  onClick={() => toggleRole(role)}
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-[11px] transition",
                    roles.includes(role)
                      ? "border-brand-400 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200"
                      : "border-border text-muted-foreground hover:text-foreground"
                  )}
                >
                  {role}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <Input
                value={customRole}
                onChange={(event) => setCustomRole(event.target.value)}
                placeholder="Custom role"
                className="h-8 text-xs"
              />
              <Button
                variant="outline"
                size="sm"
                disabled={!customRole.trim()}
                onClick={() => {
                  const value = customRole.trim()
                  if (value && !roles.includes(value))
                    setRoles([...roles, value])
                  setCustomRole("")
                }}
              >
                <Plus className="size-3" /> Add
              </Button>
            </div>
            {roles
              .filter((role) => !BUILTIN_ROLES.includes(role))
              .map((role) => (
                <button
                  type="button"
                  key={role}
                  onClick={() => toggleRole(role)}
                  className="mr-1 rounded-full bg-muted px-2.5 py-1 text-[11px]"
                >
                  {role} ×
                </button>
              ))}
          </div>
        </div>
        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-background/95 p-4 backdrop-blur">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!canSave || create.isPending}
            onClick={() => void save()}
          >
            {create.isPending ? "Creating…" : "Create Dossier"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
