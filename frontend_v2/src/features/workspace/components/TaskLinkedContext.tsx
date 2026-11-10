import { lazy, Suspense, useState } from "react"
import { ChevronRight, FileText, FolderOpen, NotebookPen } from "lucide-react"
import type { TaskLink } from "../api"
import type { DossierSource } from "@/features/dossiers/components/DossierSourceViewer"

const DossierDetailSheet = lazy(() =>
  import("@/features/dossiers/components/DossierDetailSheet").then((m) => ({
    default: m.DossierDetailSheet,
  }))
)
const CaseworkDetailSheet = lazy(() =>
  import("./CaseworkDetailSheet").then((m) => ({
    default: m.CaseworkDetailSheet,
  }))
)
const SourceViewer = lazy(() =>
  import("@/features/dossiers/components/DossierSourceViewer").then((m) => ({
    default: m.DossierSourceViewer,
  }))
)

/** Keep the task and its draft open while consulting the work that prompted it. */
export function TaskLinkedContext({
  caseId,
  links,
  canEdit,
  onBeforeNavigate,
}: {
  caseId: string
  links: TaskLink[]
  canEdit: boolean
  onBeforeNavigate?: () => boolean
}) {
  const [entryId, setEntryId] = useState<string | null>(null)
  const [dossierId, setDossierId] = useState<string | null>(null)
  const [source, setSource] = useState<DossierSource | null>(null)
  const openEvidence = (
    id: string,
    name: string,
    anchor: Record<string, unknown> = {}
  ) =>
    setSource({
      evidenceId: id,
      name,
      page: typeof anchor.page === "number" ? anchor.page : undefined,
      time:
        typeof anchor.start_seconds === "number"
          ? anchor.start_seconds
          : undefined,
    })
  if (!links.length) return null
  return (
    <section
      aria-label="Linked context"
      className="border-t border-border/60 pt-4"
    >
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        Linked context
      </h3>
      <div className="divide-y divide-border/50">
        {links.map((link) => {
          const kind =
            link.target_type === "dossier"
              ? "Dossier"
              : link.target_type === "entry"
                ? "Casework"
                : "Evidence"
          const Icon =
            link.target_type === "dossier"
              ? FolderOpen
              : link.target_type === "entry"
                ? NotebookPen
                : FileText
          return (
            <button
              key={link.id ?? `${link.target_type}:${link.target_id}`}
              type="button"
              aria-label={`Open ${link.label || `linked ${kind.toLowerCase()}`} (${kind.toLowerCase()})`}
              className="flex min-h-11 w-full items-center gap-3 rounded-sm py-2 text-left text-sm hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => {
                if (link.target_type === "dossier") setDossierId(link.target_id)
                else if (link.target_type === "entry")
                  setEntryId(link.target_id)
                else
                  openEvidence(
                    link.target_id,
                    link.label || "Source evidence",
                    link.source_anchor
                  )
              }}
            >
              <Icon
                aria-hidden="true"
                className="size-4 shrink-0 text-muted-foreground"
              />
              <span className="min-w-0 flex-1 break-words">
                {link.label || `Linked ${kind.toLowerCase()}`}
                <span className="ml-2 text-xs text-muted-foreground">
                  {kind}
                </span>
              </span>
              <ChevronRight
                aria-hidden="true"
                className="size-4 shrink-0 text-muted-foreground"
              />
            </button>
          )
        })}
      </div>
      <Suspense
        fallback={
          <p role="status" className="py-2 text-xs text-muted-foreground">
            Opening linked context…
          </p>
        }
      >
        {entryId && (
          <CaseworkDetailSheet
            caseId={caseId}
            entryId={entryId}
            open
            canEdit={canEdit}
            onOpenChange={(open) => {
              if (!open) setEntryId(null)
            }}
            onOpenEntry={setEntryId}
            onOpenDossier={setDossierId}
            onOpenEvidence={openEvidence}
            onBeforeNavigate={onBeforeNavigate}
          />
        )}
        {dossierId && (
          <DossierDetailSheet
            caseId={caseId}
            dossierId={dossierId}
            open
            canEdit={canEdit}
            onBeforeNavigate={onBeforeNavigate}
            onOpenChange={(open) => {
              if (!open) setDossierId(null)
            }}
          />
        )}
        {source && (
          <SourceViewer
            caseId={caseId}
            source={source}
            onClose={() => setSource(null)}
          />
        )}
      </Suspense>
    </section>
  )
}
