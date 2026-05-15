import { Archive, FileText, GitBranch, NotebookText, RotateCcw, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Separator } from "@/components/ui/separator"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useArchiveCaseProfile, useCaseProfileContext, useDeleteCaseProfile, useRestoreCaseProfile } from "../hooks/use-case-profiles"
import { CaseProfileTypeBadge } from "./CaseProfilePicker"

interface CaseProfileDetailDrawerProps {
  caseId: string
  profileId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onEdit?: (profileId: string) => void
  onDeleted?: (profileId: string) => void
}

function formatDate(value?: string | null) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

function nodeText(node: Record<string, unknown> | null) {
  if (!node) return "Missing graph node"
  if (typeof node.error === "string") return node.error
  return String(node.name || node.key || "Graph node")
}

export function CaseProfileDetailDrawer({
  caseId,
  profileId,
  open,
  onOpenChange,
  onEdit,
  onDeleted,
}: CaseProfileDetailDrawerProps) {
  const { data, isLoading } = useCaseProfileContext(open ? profileId : null)
  const archiveProfile = useArchiveCaseProfile(caseId)
  const restoreProfile = useRestoreCaseProfile(caseId)
  const deleteProfile = useDeleteCaseProfile(caseId)
  const profile = data?.profile

  const handleDelete = () => {
    if (!profileId) return
    deleteProfile.mutate(profileId, {
      onSuccess: () => {
        onDeleted?.(profileId)
        onOpenChange(false)
      },
    })
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full p-0 sm:max-w-xl">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <LoadingSpinner />
          </div>
        ) : profile ? (
          <>
            <SheetHeader className="border-b border-border p-4">
              <div className="flex items-start justify-between gap-3 pr-8">
                <div className="min-w-0">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <CaseProfileTypeBadge type={profile.profile_type} />
                    {profile.importance ? (
                      <Badge variant="amber">{profile.importance}</Badge>
                    ) : null}
                    {profile.archived_at ? (
                      <Badge variant="warning">
                        <Archive className="size-3" />
                        Archived
                      </Badge>
                    ) : null}
                  </div>
                  <SheetTitle className="truncate text-base">{profile.display_name}</SheetTitle>
                  <SheetDescription>
                    {profile.aliases.length > 0 ? profile.aliases.join(", ") : "Case Profile"}
                  </SheetDescription>
                </div>
                <div className="flex shrink-0 gap-1">
                  {profile.archived_at ? (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Restore"
                      onClick={() => restoreProfile.mutate(profile.id)}
                    >
                      <RotateCcw className="size-4" />
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="Archive"
                      onClick={() => archiveProfile.mutate(profile.id)}
                    >
                      <Archive className="size-4" />
                    </Button>
                  )}
                  {onEdit ? (
                    <Button variant="outline" size="sm" onClick={() => onEdit(profile.id)}>
                      Edit
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    title="Delete"
                    onClick={handleDelete}
                    disabled={deleteProfile.isPending}
                  >
                    <Trash2 className="size-4 text-red-500" />
                  </Button>
                </div>
              </div>
            </SheetHeader>

            <ScrollArea className="h-[calc(100vh-92px)]">
              <div className="space-y-4 p-4">
                {profile.summary ? (
                  <section>
                    <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                      Summary
                    </h3>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                      {profile.summary}
                    </p>
                  </section>
                ) : null}

                {profile.tags.length > 0 ? (
                  <section>
                    <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                      Tags
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.tags.map((tag) => (
                        <Badge key={tag} variant="slate">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </section>
                ) : null}

                {profile.attributes.filter((attr) => attr.kind !== "alias" && attr.kind !== "tag").length > 0 ? (
                  <section>
                    <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                      Details
                    </h3>
                    <div className="divide-y divide-border rounded-md border border-border">
                      {profile.attributes
                        .filter((attr) => attr.kind !== "alias" && attr.kind !== "tag")
                        .map((attr) => (
                          <div key={attr.id} className="grid grid-cols-[9rem_1fr] gap-3 px-3 py-2 text-sm">
                            <span className="truncate text-muted-foreground">
                              {attr.name || attr.kind}
                            </span>
                            <span className="min-w-0 break-words">{attr.value}</span>
                          </div>
                        ))}
                    </div>
                  </section>
                ) : null}

                <Separator />

                <section>
                  <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <GitBranch className="size-3.5" />
                    Graph Nodes
                  </h3>
                  {data.graph_nodes.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No graph nodes linked.</p>
                  ) : (
                    <div className="space-y-2">
                      {data.graph_nodes.map((item) => (
                        <div key={item.link.id} className="rounded-md border border-border px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="min-w-0 truncate text-sm font-medium">
                              {nodeText(item.node)}
                            </span>
                            {item.link.node_type ? (
                              <Badge variant="outline">{item.link.node_type}</Badge>
                            ) : null}
                          </div>
                          <p className="mt-1 truncate text-xs text-muted-foreground">
                            {item.link.node_key}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section>
                  <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <FileText className="size-3.5" />
                    Evidence
                  </h3>
                  {data.evidence_links.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No evidence linked.</p>
                  ) : (
                    <div className="space-y-2">
                      {data.evidence_links.map((link) => (
                        <div key={link.id} className="rounded-md border border-border px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="min-w-0 truncate text-sm font-medium">
                              {link.evidence?.original_filename || link.evidence_file_id}
                            </span>
                            {link.evidence?.status ? (
                              <Badge variant="slate">{link.evidence.status}</Badge>
                            ) : null}
                          </div>
                          {link.excerpt ? (
                            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                              {link.excerpt}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section>
                  <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <NotebookText className="size-3.5" />
                    Notes & Findings
                  </h3>
                  {[...data.notes, ...data.findings].length === 0 ? (
                    <p className="text-sm text-muted-foreground">No notes or findings linked.</p>
                  ) : (
                    <div className="space-y-2">
                      {[...data.notes, ...data.findings].map((item) => (
                        <div key={item.id} className="rounded-md border border-border px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="min-w-0 truncate text-sm font-medium">
                              {item.title || item.id}
                            </span>
                            {formatDate(item.updated_at) ? (
                              <span className="text-xs text-muted-foreground">
                                {formatDate(item.updated_at)}
                              </span>
                            ) : null}
                          </div>
                          {item.content ? (
                            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                              {item.content}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                {data.timeline_nodes.length > 0 ? (
                  <section>
                    <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                      Timeline
                    </h3>
                    <div className="space-y-2">
                      {data.timeline_nodes.map((node, index) => (
                        <div key={`${String(node.key || index)}-${index}`} className="grid grid-cols-[7rem_1fr] gap-3 text-sm">
                          <span className="text-muted-foreground">
                            {String(node.date || "")}
                          </span>
                          <span className="min-w-0 truncate">
                            {String(node.name || node.key || "Timeline node")}
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}
              </div>
            </ScrollArea>
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Case profile not found
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
