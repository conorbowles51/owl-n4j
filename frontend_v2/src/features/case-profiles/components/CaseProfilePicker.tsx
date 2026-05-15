import { useMemo, useState } from "react"
import { Archive, Check, Search, UserRound } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/cn"
import { useCaseProfiles } from "../hooks/use-case-profiles"
import type { CaseProfile, CaseProfileType } from "../types"

interface CaseProfilePickerProps {
  caseId: string
  selectedProfileIds?: string[]
  profileType?: CaseProfileType
  includeArchived?: boolean
  placeholder?: string
  className?: string
  onSelect: (profile: CaseProfile) => void
}

const profileTypeLabels: Record<CaseProfileType, string> = {
  person: "Person",
  address: "Address",
  event: "Event",
  device: "Device",
  organisation: "Organisation",
  vehicle: "Vehicle",
  other: "Other",
}

export function CaseProfileTypeBadge({ type }: { type: CaseProfileType }) {
  const variant = type === "person" || type === "organisation" ? "info" : "slate"
  return (
    <Badge variant={variant} className="text-[10px]">
      {profileTypeLabels[type]}
    </Badge>
  )
}

export function CaseProfilePicker({
  caseId,
  selectedProfileIds = [],
  profileType,
  includeArchived = false,
  placeholder = "Search case profiles...",
  className,
  onSelect,
}: CaseProfilePickerProps) {
  const [search, setSearch] = useState("")
  const selected = useMemo(() => new Set(selectedProfileIds), [selectedProfileIds])
  const { data, isLoading } = useCaseProfiles({
    caseId,
    q: search,
    profileType,
    includeArchived,
    limit: 50,
  })

  const profiles = data?.profiles ?? []

  return (
    <Command className={cn("rounded-md border border-border bg-background", className)} shouldFilter={false}>
      <CommandInput
        value={search}
        onValueChange={setSearch}
        placeholder={placeholder}
      />
      <CommandList>
        <ScrollArea className="max-h-72">
          <CommandEmpty>
            {isLoading ? "Loading case profiles..." : "No case profiles found"}
          </CommandEmpty>
          {profiles.map((profile) => {
            const isSelected = selected.has(profile.id)
            return (
              <CommandItem
                key={profile.id}
                value={`${profile.display_name} ${profile.aliases.join(" ")}`}
                onSelect={() => onSelect(profile)}
                className="items-start gap-3 px-3 py-2"
              >
                <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
                  {isSelected ? (
                    <Check className="size-3.5 text-emerald-600" />
                  ) : (
                    <UserRound className="size-3.5 text-muted-foreground" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium">{profile.display_name}</span>
                    <CaseProfileTypeBadge type={profile.profile_type} />
                    {profile.archived_at ? (
                      <Badge variant="warning" className="text-[10px]">
                        <Archive className="size-3" />
                        Archived
                      </Badge>
                    ) : null}
                  </div>
                  {profile.aliases.length > 0 ? (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {profile.aliases.join(", ")}
                    </p>
                  ) : null}
                  {profile.summary ? (
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {profile.summary}
                    </p>
                  ) : null}
                </div>
              </CommandItem>
            )
          })}
          {!isLoading && profiles.length === 0 && search ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <Search className="size-4" />
              No matches
            </div>
          ) : null}
        </ScrollArea>
      </CommandList>
    </Command>
  )
}
