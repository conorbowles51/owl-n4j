import { useMemo, useState } from "react"
import { Archive, Check, FolderSearch, UserRound } from "lucide-react"
import { useQuery } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
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

import { dossiersAPI, type Dossier } from "../api"

const typeLabels: Record<string, string> = {
  person: "Person",
  address: "Address",
  event: "Event",
  device: "Device",
  organisation: "Organisation",
  vehicle: "Vehicle",
  other: "Other",
}

export function DossierTypeBadge({ type }: { type: string }) {
  const variant =
    type === "person" || type === "organisation" ? "info" : "slate"
  return (
    <Badge variant={variant} className="text-[10px]">
      {typeLabels[type] ?? type}
    </Badge>
  )
}

export function DossierPicker({
  caseId,
  selectedDossierIds = [],
  placeholder = "Search Dossiers...",
  className,
  onSelect,
}: {
  caseId: string
  selectedDossierIds?: string[]
  placeholder?: string
  className?: string
  onSelect: (dossier: Dossier) => void
}) {
  const [search, setSearch] = useState("")
  const [offset, setOffset] = useState(0)
  const selected = useMemo(
    () => new Set(selectedDossierIds),
    [selectedDossierIds]
  )
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dossiers", "picker", caseId, search, offset],
    queryFn: () => dossiersAPI.list({ caseId, q: search, limit: 50, offset }),
    enabled: Boolean(caseId),
  })

  return (
    <Command
      className={cn("rounded-md border border-border bg-background", className)}
      shouldFilter={false}
    >
      <CommandInput
        value={search}
        onValueChange={(value) => {
          setSearch(value)
          setOffset(0)
        }}
        placeholder={placeholder}
      />
      {isError && (
        <div role="alert" className="p-3 text-xs">
          Dossiers could not be loaded.{" "}
          <Button variant="ghost" size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      )}
      <CommandList>
        <ScrollArea className="max-h-72">
          <CommandEmpty>
            {isLoading
              ? "Loading Dossiers..."
              : isError
                ? "Dossiers unavailable"
                : "No Dossiers found"}
          </CommandEmpty>
          {(data?.dossiers ?? []).map((dossier) => {
            const isSelected = selected.has(dossier.id)
            return (
              <CommandItem
                key={dossier.id}
                value={`${dossier.display_name} ${dossier.summary ?? ""}`}
                onSelect={() => onSelect(dossier)}
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
                    <span className="truncate text-sm font-medium">
                      {dossier.display_name}
                    </span>
                    <DossierTypeBadge type={dossier.dossier_type} />
                    {dossier.archived_at ? (
                      <Badge variant="warning" className="text-[10px]">
                        <Archive className="size-3" /> Archived
                      </Badge>
                    ) : null}
                  </div>
                  {dossier.summary ? (
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {dossier.summary}
                    </p>
                  ) : null}
                </div>
              </CommandItem>
            )
          })}
          {!isLoading && !data?.dossiers.length && search ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <FolderSearch className="size-4" /> No matches
            </div>
          ) : null}
        </ScrollArea>
      </CommandList>
      {data && data.total > 50 && (
        <div className="flex items-center justify-between border-t p-2 text-xs">
          <Button
            variant="ghost"
            size="sm"
            disabled={offset === 0 || isLoading}
            onClick={() => setOffset((value) => Math.max(0, value - 50))}
          >
            Previous dossiers
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={offset + 50 >= data.total || isLoading}
            onClick={() => setOffset((value) => value + 50)}
          >
            Next dossiers
          </Button>
        </div>
      )}
    </Command>
  )
}
