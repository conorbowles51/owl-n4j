import { useState } from "react"
import { useUnsavedHistoryGuard } from "@/hooks/use-unsaved-history-guard"
import { useQuery } from "@tanstack/react-query"
import { Check, FileText, Lightbulb, Search, SearchCheck } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  caseworkAPI,
  type CaseworkEntryType,
} from "@/features/workspace/casework-api"
import { dossiersAPI, type Dossier } from "../api"
import { useDossierMutation } from "../hooks"

const PAGE_SIZE = 30
const kinds = {
  note: { label: "Note", icon: FileText },
  finding: { label: "Finding", icon: SearchCheck },
  theory: { label: "Theory", icon: Lightbulb },
}

/** Append existing work by reference. Never replace the dossier's other collected material. */
export function AddDossierCaseworkDialog({
  dossier,
  onClose,
  onSaved,
}: {
  dossier: Dossier
  onClose: () => void
  onSaved: () => void
}) {
  const [search, setSearch] = useState("")
  const [kind, setKind] = useState<CaseworkEntryType | undefined>()
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [error, setError] = useState("")
  const query = useQuery({
    queryKey: [
      "casework",
      dossier.case_id,
      "dossier-picker",
      search,
      kind,
      offset,
    ],
    queryFn: () =>
      caseworkAPI.list(dossier.case_id, {
        q: search.trim() || undefined,
        entry_type: kind,
        limit: PAGE_SIZE,
        offset,
      }),
  })
  const linked = new Set([
    ...(dossier.links ?? [])
      .filter((link) => link.target_type === "entry")
      .map((link) => link.target_id),
    ...(dossier.incoming_casework ?? []).map((entry) => entry.id),
  ])
  const add = useDossierMutation(dossier.case_id, dossier.id, () =>
    dossiersAPI.addLinks(
      dossier.id,
      Object.entries(selected).map(([id, label]) => ({
        target_type: "entry",
        target_id: id,
        label,
      }))
    )
  )
  const count = Object.keys(selected).length
  const discardMessage = "Discard your selected casework without linking it?"
  useUnsavedHistoryGuard(count > 0 || add.isPending, discardMessage)
  const close = () => {
    if (!add.isPending && (!count || window.confirm(discardMessage))) onClose()
  }
  const save = async () => {
    setError("")
    try {
      await add.mutateAsync(undefined)
      toast.success(
        `${count === 1 ? "Item" : "Items"} added to ${dossier.display_name}`
      )
      onSaved()
      onClose()
    } catch {
      setError(
        "Could not link this casework. Your selection is kept here. Try again."
      )
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close()
      }}
    >
      <DialogContent
        guardTypedContent={false}
        className="flex max-h-[calc(100dvh-2rem)] flex-col gap-4 sm:max-w-xl"
      >
        <DialogHeader>
          <DialogTitle>Add casework to {dossier.display_name}</DialogTitle>
          <DialogDescription>
            Collect notes, findings and theories from this case. Changes to the
            original work remain available here.
          </DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Search casework"
            placeholder="Search casework…"
            className="h-10 pl-9"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setOffset(0)
            }}
          />
        </div>
        <div className="flex flex-wrap gap-1" aria-label="Casework types">
          {([undefined, "note", "finding", "theory"] as const).map((value) => (
            <Button
              key={value ?? "all"}
              variant={kind === value ? "secondary" : "ghost"}
              className="min-h-10"
              aria-pressed={kind === value}
              onClick={() => {
                setKind(value)
                setOffset(0)
              }}
            >
              {value
                ? value === "theory"
                  ? "Theories"
                  : `${kinds[value].label}s`
                : "All work"}
            </Button>
          ))}
        </div>
        <div
          className="min-h-0 overflow-y-auto border-y border-border/75"
          aria-live="polite"
        >
          {query.isLoading ? (
            <p className="p-6 text-center text-sm text-muted-foreground">
              Loading casework…
            </p>
          ) : query.isError ? (
            <div role="alert" className="p-5 text-sm">
              Casework could not be loaded.{" "}
              <Button variant="ghost" onClick={() => void query.refetch()}>
                Retry casework
              </Button>
            </div>
          ) : query.data?.entries.length ? (
            query.data.entries.map((entry) => {
              const title =
                entry.title || entry.body.slice(0, 100) || "Untitled casework"
              const alreadyLinked = linked.has(entry.id)
              const isSelected = Object.hasOwn(selected, entry.id)
              const { icon: Icon, label } = kinds[entry.entry_type]
              return (
                <button
                  type="button"
                  key={entry.id}
                  disabled={alreadyLinked || add.isPending}
                  aria-pressed={isSelected || alreadyLinked}
                  onClick={() =>
                    setSelected((previous) => {
                      const next = { ...previous }
                      if (isSelected) delete next[entry.id]
                      else next[entry.id] = title
                      return next
                    })
                  }
                  className="flex w-full items-start gap-3 border-b border-border/50 px-2 py-4 text-left last:border-0 hover:bg-muted/30 disabled:opacity-60"
                >
                  <Icon
                    aria-hidden="true"
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs text-muted-foreground">
                      {label}
                    </span>
                    <span className="mt-0.5 block break-words text-sm font-medium">
                      {title}
                    </span>
                  </span>
                  <span className="flex min-h-6 shrink-0 items-center gap-1 text-xs text-muted-foreground">
                    {alreadyLinked
                      ? "Added"
                      : isSelected
                        ? "Selected"
                        : "Select"}
                    {(alreadyLinked || isSelected) && (
                      <Check className="size-4" />
                    )}
                  </span>
                </button>
              )
            })
          ) : (
            <p className="p-6 text-center text-sm text-muted-foreground">
              {search || kind
                ? "No casework matches these filters."
                : "No casework yet. Save a note, finding or theory in Workspace first."}
            </p>
          )}
        </div>
        {(offset > 0 || (query.data?.total ?? 0) > PAGE_SIZE) && (
          <div className="flex items-center justify-between gap-2 text-xs">
            <Button
              variant="ghost"
              disabled={!offset || query.isLoading}
              onClick={() =>
                setOffset((value) => Math.max(0, value - PAGE_SIZE))
              }
            >
              Previous work
            </Button>
            <span className="tabular-nums">
              {offset + 1}–
              {Math.min(offset + PAGE_SIZE, query.data?.total ?? offset)} of{" "}
              {query.data?.total ?? "…"}
            </span>
            <Button
              variant="ghost"
              disabled={
                query.isLoading ||
                offset + PAGE_SIZE >= (query.data?.total ?? 0)
              }
              onClick={() => setOffset((value) => value + PAGE_SIZE)}
            >
              Next work
            </Button>
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <DialogFooter className="items-center">
          <span className="mr-auto text-xs text-muted-foreground">
            {count} selected
          </span>
          <Button variant="ghost" disabled={add.isPending} onClick={close}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!count || add.isPending}
            onClick={() => void save()}
          >
            {add.isPending
              ? "Linking…"
              : error
                ? "Retry linking"
                : `Link ${count} ${count === 1 ? "item" : "items"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
