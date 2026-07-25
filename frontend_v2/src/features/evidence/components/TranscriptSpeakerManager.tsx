import { useState } from "react"
import {
  GitMerge,
  MoreHorizontal,
  Pencil,
  RotateCcw,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import type { TranscriptSpeakerGroup } from "./audio-transcript.utils"

interface TranscriptSpeakerManagerProps {
  groups: TranscriptSpeakerGroup[]
  fallbackNames: Map<string, string>
  saving?: boolean
  onRename: (speaker: string, name: string) => Promise<void>
  onMerge: (
    sourceSpeaker: string,
    targetSpeaker: string,
    combinedName: string
  ) => Promise<void>
  onUnmerge: (rawSpeaker: string) => Promise<void>
}

interface MergeSelection {
  sourceSpeaker: string
  targetSpeaker: string
}

function formatDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds))
  if (rounded < 60) return `${rounded}s`
  const minutes = Math.floor(rounded / 60)
  const remainder = rounded % 60
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`
}

export function TranscriptSpeakerManager({
  groups,
  fallbackNames,
  saving = false,
  onRename,
  onMerge,
  onUnmerge,
}: TranscriptSpeakerManagerProps) {
  const [renameSpeaker, setRenameSpeaker] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState("")
  const [mergeSelection, setMergeSelection] = useState<MergeSelection | null>(
    null
  )
  const [mergeNameDraft, setMergeNameDraft] = useState("")

  const rawSpeakerCount = groups.reduce(
    (total, group) => total + group.members.length,
    0
  )
  const renameGroup = groups.find(
    (group) => group.canonicalSpeaker === renameSpeaker
  )
  const mergeSource = groups.find(
    (group) =>
      group.canonicalSpeaker === mergeSelection?.sourceSpeaker
  )
  const mergeTarget = groups.find(
    (group) =>
      group.canonicalSpeaker === mergeSelection?.targetSpeaker
  )

  const startRename = (group: TranscriptSpeakerGroup) => {
    setRenameSpeaker(group.canonicalSpeaker)
    setRenameDraft(group.displayName)
  }

  const startMerge = (
    source: TranscriptSpeakerGroup,
    target: TranscriptSpeakerGroup
  ) => {
    setMergeSelection({
      sourceSpeaker: source.canonicalSpeaker,
      targetSpeaker: target.canonicalSpeaker,
    })
    setMergeNameDraft(target.displayName)
  }

  const saveRename = async () => {
    if (!renameSpeaker) return
    try {
      await onRename(renameSpeaker, renameDraft)
      setRenameSpeaker(null)
    } catch {
      // The parent reports persistence errors and restores the previous state.
    }
  }

  const saveMerge = async () => {
    if (!mergeSelection) return
    try {
      await onMerge(
        mergeSelection.sourceSpeaker,
        mergeSelection.targetSpeaker,
        mergeNameDraft
      )
      setMergeSelection(null)
    } catch {
      // Keep the dialog open so the investigator can retry.
    }
  }

  const restoreSpeaker = async (rawSpeaker: string) => {
    try {
      await onUnmerge(rawSpeaker)
    } catch {
      // The parent reports persistence errors and restores the previous state.
    }
  }

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 text-xs"
            aria-label={`Manage ${groups.length} transcript speakers`}
          >
            <Users className="size-3.5" />
            {groups.length} {groups.length === 1 ? "speaker" : "speakers"}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-[380px] overflow-hidden p-0">
          <PopoverHeader className="border-b border-border/70 px-4 py-3">
            <PopoverTitle className="flex items-center gap-2">
              <Users className="size-4 text-amber-600 dark:text-amber-400" />
              Manage speakers
            </PopoverTitle>
            <PopoverDescription>
              Rename detected voices or combine labels that belong to the same
              person.
            </PopoverDescription>
          </PopoverHeader>

          <div className="max-h-[min(430px,60vh)] overflow-y-auto p-2">
            {groups.map((group) => {
              const aliases = group.members.filter(
                (member) => member !== group.canonicalSpeaker
              )
              return (
                <div
                  key={group.canonicalSpeaker}
                  className="rounded-lg border border-transparent px-2 py-2.5 hover:border-border/70 hover:bg-muted/40"
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-1.5 size-2 shrink-0 rounded-full bg-amber-500" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">
                        {group.displayName}
                      </p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {group.turns} {group.turns === 1 ? "turn" : "turns"}
                        {" · "}
                        {formatDuration(group.duration)}
                      </p>
                      {group.members.length > 1 && (
                        <p className="mt-1.5 text-[10px] leading-4 text-muted-foreground">
                          Combined from{" "}
                          {group.members
                            .map(
                              (member) =>
                                fallbackNames.get(member) || member
                            )
                            .join(" + ")}
                        </p>
                      )}
                    </div>

                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          disabled={saving}
                          aria-label={`Actions for ${group.displayName}`}
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-56">
                        <DropdownMenuItem onSelect={() => startRename(group)}>
                          <Pencil className="size-3.5" />
                          Rename
                        </DropdownMenuItem>
                        {groups.length > 1 && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel className="text-xs text-muted-foreground">
                              Merge into
                            </DropdownMenuLabel>
                            {groups
                              .filter(
                                (candidate) =>
                                  candidate.canonicalSpeaker !==
                                  group.canonicalSpeaker
                              )
                              .map((candidate) => (
                                <DropdownMenuItem
                                  key={candidate.canonicalSpeaker}
                                  onSelect={() =>
                                    startMerge(group, candidate)
                                  }
                                >
                                  <GitMerge className="size-3.5" />
                                  <span className="truncate">
                                    {candidate.displayName}
                                  </span>
                                </DropdownMenuItem>
                              ))}
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>

                  {aliases.length > 0 && (
                    <div className="ml-5 mt-2 flex flex-wrap gap-1.5">
                      {aliases.map((rawSpeaker) => (
                        <button
                          key={rawSpeaker}
                          type="button"
                          disabled={saving}
                          onClick={() => void restoreSpeaker(rawSpeaker)}
                          className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-background px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:border-amber-500/50 hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
                          title={`Split ${
                            fallbackNames.get(rawSpeaker) || rawSpeaker
                          } back out`}
                        >
                          <RotateCcw className="size-2.5" />
                          Restore {fallbackNames.get(rawSpeaker) || rawSpeaker}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {rawSpeakerCount > groups.length && (
            <div className="border-t border-border/70 bg-muted/30 px-4 py-2.5 text-[10px] text-muted-foreground">
              Showing {groups.length} people from {rawSpeakerCount} original
              diarization labels. Original labels remain preserved.
            </div>
          )}
        </PopoverContent>
      </Popover>

      <Dialog
        open={Boolean(renameSpeaker)}
        onOpenChange={(open) => {
          if (!open && !saving) setRenameSpeaker(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename speaker</DialogTitle>
            <DialogDescription>
              This name will be shown on all {renameGroup?.turns ?? 0} turns
              assigned to this speaker.
            </DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={renameDraft}
            maxLength={80}
            onChange={(event) => setRenameDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void saveRename()
            }}
            aria-label="Speaker name"
          />
          <DialogFooter>
            <Button
              variant="outline"
              disabled={saving}
              onClick={() => setRenameSpeaker(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={saving || !renameDraft.trim()}
              onClick={() => void saveRename()}
            >
              Save name
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(mergeSelection)}
        onOpenChange={(open) => {
          if (!open && !saving) setMergeSelection(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Merge these speakers?</DialogTitle>
            <DialogDescription>
              All turns currently labelled {mergeSource?.displayName} will be
              shown as {mergeTarget?.displayName}. Transcript text, timestamps,
              and the original diarization labels will not be changed.
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2.5 text-sm">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-medium">
                {mergeSource?.displayName}
              </span>
              <GitMerge className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
              <span className="min-w-0 flex-1 truncate text-right font-medium">
                {mergeTarget?.displayName}
              </span>
            </div>
          </div>

          <label className="space-y-1.5">
            <span className="text-xs font-medium">Combined speaker name</span>
            <Input
              value={mergeNameDraft}
              maxLength={80}
              onChange={(event) => setMergeNameDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && mergeNameDraft.trim()) {
                  void saveMerge()
                }
              }}
              aria-label="Combined speaker name"
            />
            <span className="block text-[11px] text-muted-foreground">
              Keep the existing name or enter the person’s real name.
            </span>
          </label>

          <DialogFooter>
            <Button
              variant="outline"
              disabled={saving}
              onClick={() => setMergeSelection(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={saving || !mergeNameDraft.trim()}
              onClick={() => void saveMerge()}
            >
              <GitMerge className="size-4" />
              Merge speakers
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
