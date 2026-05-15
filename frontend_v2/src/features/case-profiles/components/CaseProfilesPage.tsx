import { useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import { Archive, Plus, Search, UserRound } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { ScrollArea } from "@/components/ui/scroll-area"
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
import { cn } from "@/lib/cn"
import {
  CaseProfileDetailDrawer,
  CaseProfileTypeBadge,
  useCaseProfiles,
  useCreateCaseProfile,
  useUpdateCaseProfile,
} from "@/features/case-profiles"
import {
  caseProfileTypes,
  type CaseProfile,
  type CaseProfileCreateInput,
  type CaseProfileType,
} from "../types"

type TypeFilter = "all" | CaseProfileType

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}

function joinList(values?: string[]) {
  return values?.join(", ") ?? ""
}

function ProfileFormSheet({
  caseId,
  profile,
  open,
  onOpenChange,
}: {
  caseId: string
  profile: CaseProfile | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createProfile = useCreateCaseProfile(caseId)
  const updateProfile = useUpdateCaseProfile(caseId, profile?.id ?? "")
  const [profileType, setProfileType] = useState<CaseProfileType>(() => profile?.profile_type ?? "person")
  const [displayName, setDisplayName] = useState(() => profile?.display_name ?? "")
  const [importance, setImportance] = useState(() => profile?.importance ?? "")
  const [aliases, setAliases] = useState(() => joinList(profile?.aliases))
  const [tags, setTags] = useState(() => joinList(profile?.tags))
  const [summary, setSummary] = useState(() => profile?.summary ?? "")

  const isSaving = createProfile.isPending || updateProfile.isPending
  const canSave = displayName.trim().length > 0 && !isSaving

  const handleSubmit = () => {
    if (!canSave) return

    const payload: Omit<CaseProfileCreateInput, "case_id"> = {
      profile_type: profileType,
      display_name: displayName.trim(),
      importance: importance.trim() || null,
      summary: summary.trim() || null,
      aliases: splitList(aliases),
      tags: splitList(tags),
    }

    if (profile) {
      updateProfile.mutate(payload, { onSuccess: () => onOpenChange(false) })
    } else {
      createProfile.mutate(payload, { onSuccess: () => onOpenChange(false) })
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full p-0 sm:max-w-lg">
        <SheetHeader className="border-b border-border p-4">
          <SheetTitle>{profile ? "Edit Case Profile" : "New Case Profile"}</SheetTitle>
          <SheetDescription>
            Link people, devices, addresses, events, and other recurring case subjects.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          <div className="grid gap-2">
            <Label htmlFor="profile-type">Type</Label>
            <Select value={profileType} onValueChange={(value) => setProfileType(value as CaseProfileType)}>
              <SelectTrigger id="profile-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {caseProfileTypes.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="display-name">Display name</Label>
            <Input
              id="display-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Jane Smith"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="importance">Importance</Label>
            <Input
              id="importance"
              value={importance}
              onChange={(event) => setImportance(event.target.value)}
              placeholder="witness, suspect, key device"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="aliases">Aliases</Label>
            <Input
              id="aliases"
              value={aliases}
              onChange={(event) => setAliases(event.target.value)}
              placeholder="Comma-separated names"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="tags">Tags</Label>
            <Input
              id="tags"
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="Comma-separated tags"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="summary">Summary</Label>
            <Textarea
              id="summary"
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="Concise profile context..."
              rows={5}
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border p-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} disabled={!canSave}>
            {isSaving ? <LoadingSpinner size="sm" /> : null}
            Save
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

export function CaseProfilesPage() {
  const { id: caseId } = useParams()
  const [search, setSearch] = useState("")
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all")
  const [includeArchived, setIncludeArchived] = useState(false)
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null)
  const [editingProfile, setEditingProfile] = useState<CaseProfile | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  const profilesQuery = useCaseProfiles(
    {
      caseId: caseId ?? "",
      q: search || undefined,
      profileType: typeFilter === "all" ? undefined : typeFilter,
      includeArchived,
      limit: 100,
    },
    Boolean(caseId)
  )

  const profiles = useMemo(() => profilesQuery.data?.profiles ?? [], [profilesQuery.data?.profiles])
  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedProfileId) ?? null,
    [profiles, selectedProfileId]
  )

  if (!caseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState title="No case selected" />
      </div>
    )
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <div className="flex h-14 items-center justify-between gap-3 border-b border-border px-5">
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold">Case Profiles</h1>
          <p className="text-xs text-muted-foreground">
            {profilesQuery.data?.total ?? 0} profiles
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            setEditingProfile(null)
            setFormOpen(true)
          }}
        >
          <Plus className="size-4" />
          New
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
        <div className="relative min-w-64 flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search profiles..."
            className="pl-9"
          />
        </div>
        <Select value={typeFilter} onValueChange={(value) => setTypeFilter(value as TypeFilter)}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {caseProfileTypes.map((type) => (
              <SelectItem key={type} value={type}>
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Checkbox
            checked={includeArchived}
            onCheckedChange={(checked) => setIncludeArchived(checked === true)}
          />
          Archived
        </label>
      </div>

      <ScrollArea className="flex-1">
        <div className="grid gap-2 p-5">
          {profilesQuery.isLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : profiles.length === 0 ? (
            <EmptyState
              title="No case profiles"
              description="Create profiles for people, devices, addresses, vehicles, events, and organisations that recur across the case."
              action={
                <Button variant="primary" onClick={() => setFormOpen(true)}>
                  <Plus className="size-4" />
                  New Profile
                </Button>
              }
            />
          ) : (
            profiles.map((profile) => (
              <button
                key={profile.id}
                type="button"
                onClick={() => setSelectedProfileId(profile.id)}
                className={cn(
                  "flex min-w-0 items-start gap-3 rounded-md border border-border bg-card px-4 py-3 text-left transition-colors hover:border-slate-300 dark:hover:border-slate-600",
                  selectedProfileId === profile.id && "border-amber-400 bg-amber-50/60 dark:bg-amber-500/10"
                )}
              >
                <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
                  <UserRound className="size-4 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold">{profile.display_name}</span>
                    <CaseProfileTypeBadge type={profile.profile_type} />
                    {profile.importance ? <Badge variant="amber">{profile.importance}</Badge> : null}
                    {profile.archived_at ? (
                      <Badge variant="warning">
                        <Archive className="size-3" />
                        Archived
                      </Badge>
                    ) : null}
                  </div>
                  {profile.summary ? (
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {profile.summary}
                    </p>
                  ) : null}
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {profile.aliases.slice(0, 3).map((alias) => (
                      <Badge key={alias} variant="outline">
                        {alias}
                      </Badge>
                    ))}
                    {profile.tags.slice(0, 4).map((tag) => (
                      <Badge key={tag} variant="slate">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </ScrollArea>

      <CaseProfileDetailDrawer
        caseId={caseId}
        profileId={selectedProfileId}
        open={Boolean(selectedProfileId)}
        onOpenChange={(open) => {
          if (!open) setSelectedProfileId(null)
        }}
        onEdit={() => {
          setEditingProfile(selectedProfile)
          setFormOpen(true)
        }}
        onDeleted={() => setSelectedProfileId(null)}
      />

      <ProfileFormSheet
        key={`${formOpen ? "open" : "closed"}:${editingProfile?.id ?? "new"}`}
        caseId={caseId}
        profile={editingProfile}
        open={formOpen}
        onOpenChange={setFormOpen}
      />
    </div>
  )
}
