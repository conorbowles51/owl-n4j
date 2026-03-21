import { useState, Suspense, lazy } from "react"
import { useParams } from "react-router-dom"
import {
  Upload,
  FolderSync,
  Activity,
  FileText,
  Settings,
  Upload as UploadIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { PageHeader } from "@/components/ui/page-header"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { useEvidence } from "../hooks/use-evidence"
import { useActiveTaskCount } from "../hooks/use-background-tasks"
import { useDeleteEvidence, useSyncFilesystem, useProcessBackground } from "../hooks/use-evidence-detail"
import { useEvidenceStore } from "../evidence.store"
import { EvidenceRow } from "./EvidenceRow"
import { EvidenceToolbar } from "./EvidenceToolbar"
import { ProcessingStatusBanner } from "./ProcessingStatusBanner"
import { EvidenceDetailSheet } from "./EvidenceDetailSheet"
import { DeleteEvidenceDialog } from "./DeleteEvidenceDialog"
import { ProcessDialog } from "./ProcessDialog"
import { UploadProcessTab } from "./UploadProcessTab"
import { ActivityTab } from "./ActivityTab"
import { toast } from "sonner"
import type { EvidenceFile } from "@/types/evidence.types"
import { getFileTypeCategory } from "../utils/file-types"

const ProfilesTab = lazy(() =>
  import("./ProfilesTab").then((m) => ({ default: m.ProfilesTab }))
)

export function EvidencePage() {
  const { id: caseId } = useParams()
  const { data: files, isLoading } = useEvidence(caseId)
  const processMutation = useProcessBackground(caseId!)
  const deleteMutation = useDeleteEvidence(caseId!)
  const syncMutation = useSyncFilesystem(caseId!)
  const activeTaskCount = useActiveTaskCount(caseId)

  const {
    selectedFileIds,
    toggleFileSelection,
    selectAllFiles,
    clearSelection,
    activeTab,
    setActiveTab,
    detailFile,
    detailOpen,
    openDetail,
    closeDetail,
    searchTerm,
    statusFilter,
    typeFilter,
  } = useEvidenceStore()

  const [deleteOpen, setDeleteOpen] = useState(false)
  const [processOpen, setProcessOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<EvidenceFile | null>(null)

  // Filter files
  const filtered = files?.filter((f) => {
    if (searchTerm && !f.original_filename.toLowerCase().includes(searchTerm.toLowerCase()))
      return false
    if (statusFilter !== "all" && f.status !== statusFilter) return false
    if (typeFilter && getFileTypeCategory(f.original_filename) !== typeFilter) return false
    return true
  })

  const toggleAll = () => {
    if (selectedFileIds.size === filtered?.length) {
      clearSelection()
    } else {
      selectAllFiles(filtered?.map((f) => f.id) ?? [])
    }
  }

  const handleSync = () => {
    syncMutation.mutate(undefined, {
      onSuccess: (data) => toast.success(`Synced ${data.synced} files`),
      onError: () => toast.error("Filesystem sync failed"),
    })
  }

  const handleBulkProcess = () => {
    if (selectedFileIds.size > 0) setProcessOpen(true)
  }

  const handleBulkDelete = () => {
    if (selectedFileIds.size > 0) setDeleteOpen(true)
  }

  const handleConfirmProcess = (config: {
    profile?: string
    maxWorkers: number
    imageProvider?: string
  }) => {
    processMutation.mutate(
      {
        fileIds: Array.from(selectedFileIds),
        ...config,
      },
      {
        onSuccess: () => {
          toast.success("Processing started")
          setProcessOpen(false)
          clearSelection()
          setActiveTab("activity")
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleConfirmDelete = (deleteExclusiveEntities: boolean) => {
    const ids = deleteTarget ? [deleteTarget.id] : Array.from(selectedFileIds)
    // Delete sequentially
    const deleteNext = (index: number) => {
      if (index >= ids.length) {
        toast.success(`Deleted ${ids.length} file${ids.length !== 1 ? "s" : ""}`)
        setDeleteOpen(false)
        setDeleteTarget(null)
        clearSelection()
        return
      }
      deleteMutation.mutate(
        { evidenceId: ids[index], deleteExclusiveEntities },
        { onSuccess: () => deleteNext(index + 1) }
      )
    }
    deleteNext(0)
  }

  const handleRowReprocess = (file: EvidenceFile) => {
    processMutation.mutate(
      { fileIds: [file.id] },
      {
        onSuccess: () => toast.success(`Reprocessing ${file.original_filename}`),
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleRowDelete = (file: EvidenceFile) => {
    setDeleteTarget(file)
    setDeleteOpen(true)
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border px-6 py-3">
        <PageHeader
          title="Evidence & Ingestion"
          actions={
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleSync}
                disabled={syncMutation.isPending}
              >
                <FolderSync className="size-3.5" />
                {syncMutation.isPending ? "Syncing..." : "Sync"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setActiveTab("upload")}
              >
                <Upload className="size-3.5" />
                Upload
              </Button>
              {activeTaskCount > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setActiveTab("activity")}
                >
                  <Activity className="size-3.5" />
                  Tasks
                  <Badge variant="info" className="ml-1 text-[10px]">
                    {activeTaskCount}
                  </Badge>
                </Button>
              )}
            </div>
          }
        />
      </div>

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as typeof activeTab)}
        className="flex flex-1 flex-col overflow-hidden"
      >
        <div className="border-b border-border px-6">
          <TabsList variant="line">
            <TabsTrigger value="files">
              <FileText className="size-3.5" />
              Files
            </TabsTrigger>
            <TabsTrigger value="upload">
              <UploadIcon className="size-3.5" />
              Upload
            </TabsTrigger>
            <TabsTrigger value="profiles">
              <Settings className="size-3.5" />
              Profiles
            </TabsTrigger>
            <TabsTrigger value="activity">
              <Activity className="size-3.5" />
              Activity
              {activeTaskCount > 0 && (
                <Badge variant="info" className="ml-1 text-[10px]">
                  {activeTaskCount}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Files Tab */}
        <TabsContent value="files" className="flex-1 flex flex-col overflow-hidden">
          <EvidenceToolbar
            onProcess={handleBulkProcess}
            onDelete={handleBulkDelete}
            processPending={processMutation.isPending}
          />
          <ProcessingStatusBanner caseId={caseId!} />

          <div className="flex-1 overflow-auto">
            {isLoading ? (
              <div className="flex justify-center py-12">
                <LoadingSpinner />
              </div>
            ) : !filtered?.length ? (
              <EmptyState
                icon={Upload}
                title="No evidence files"
                description={
                  searchTerm || statusFilter !== "all"
                    ? "No files match the current filters"
                    : "Upload files to begin processing evidence"
                }
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8">
                      <Checkbox
                        checked={
                          selectedFileIds.size > 0 &&
                          selectedFileIds.size === filtered.length
                        }
                        onCheckedChange={toggleAll}
                      />
                    </TableHead>
                    <TableHead>Filename</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Entities</TableHead>
                    <TableHead>Uploaded</TableHead>
                    <TableHead className="w-24" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((file) => (
                    <EvidenceRow
                      key={file.id}
                      file={file}
                      selected={selectedFileIds.has(file.id)}
                      onSelect={toggleFileSelection}
                      onView={openDetail}
                      onReprocess={handleRowReprocess}
                      onDelete={handleRowDelete}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </TabsContent>

        {/* Upload & Process Tab */}
        <TabsContent value="upload" className="flex-1 overflow-auto">
          <UploadProcessTab caseId={caseId!} />
        </TabsContent>

        {/* Profiles Tab */}
        <TabsContent value="profiles" className="flex-1 overflow-auto">
          <Suspense
            fallback={
              <div className="flex justify-center py-12">
                <LoadingSpinner />
              </div>
            }
          >
            <ProfilesTab />
          </Suspense>
        </TabsContent>

        {/* Activity Tab */}
        <TabsContent value="activity" className="flex-1 overflow-hidden">
          <ActivityTab caseId={caseId!} />
        </TabsContent>
      </Tabs>

      {/* Detail Sheet */}
      <EvidenceDetailSheet
        file={detailFile}
        open={detailOpen}
        onOpenChange={(open) => {
          if (!open) closeDetail()
        }}
        caseId={caseId!}
        onReprocess={handleRowReprocess}
        onDelete={handleRowDelete}
      />

      {/* Delete Dialog */}
      <DeleteEvidenceDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        fileCount={deleteTarget ? 1 : selectedFileIds.size}
        onConfirm={handleConfirmDelete}
        isPending={deleteMutation.isPending}
      />

      {/* Process Dialog */}
      <ProcessDialog
        open={processOpen}
        onOpenChange={setProcessOpen}
        fileCount={selectedFileIds.size}
        onConfirm={handleConfirmProcess}
        isPending={processMutation.isPending}
      />
    </div>
  )
}
