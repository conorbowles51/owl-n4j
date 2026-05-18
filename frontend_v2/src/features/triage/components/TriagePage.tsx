import { useMemo, useState, type FormEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertCircle,
  ArrowLeft,
  BarChart3,
  BookTemplate,
  Check,
  CheckCircle2,
  ChevronRight,
  ChevronUp,
  Cpu,
  Database,
  File,
  FileSearch,
  FileText,
  Filter,
  Folder,
  FolderInput,
  FolderOpen,
  HardDrive,
  Layers,
  Loader2,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Send,
  Shield,
  Sparkles,
  Trash2,
  Upload,
  Users,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { casesAPI } from "@/features/cases/api"
import { cn } from "@/lib/cn"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { triageAPI } from "../api"
import {
  formatBytes,
  formatDateTime,
  isRunningStatus,
  normalizeCategoryRows,
  stageProgress,
} from "../lib/format"
import type {
  AdvisorSuggestion,
  Artifact,
  ClassificationStats,
  DirectoryEntry,
  ProcessorInfo,
  ScanStats,
  TriageCase,
  TriageFile,
  TriageFileListParams,
  TriageProfile,
  TriageStage,
  TriageTemplate,
} from "../triage.types"

const CATEGORY_COLORS: Record<string, string> = {
  documents: "bg-sky-500",
  images: "bg-fuchsia-500",
  video: "bg-rose-500",
  audio: "bg-amber-500",
  archives: "bg-slate-500",
  executables: "bg-red-500",
  databases: "bg-emerald-500",
  emails: "bg-cyan-500",
  web: "bg-orange-500",
  system: "bg-zinc-400",
  other: "bg-stone-400",
}

const CATEGORIES = [
  "documents",
  "images",
  "video",
  "audio",
  "archives",
  "executables",
  "databases",
  "emails",
  "web",
  "system",
  "other",
]

const TRIAGE_INGEST_DISABLED_MESSAGE =
  "Triage ingest is paused until it is routed through the evidence engine."

function invalidateTriage(queryClient: ReturnType<typeof useQueryClient>, caseId?: string) {
  queryClient.invalidateQueries({ queryKey: ["triage-cases"] })
  if (caseId) {
    queryClient.invalidateQueries({ queryKey: ["triage-case", caseId] })
    queryClient.invalidateQueries({ queryKey: ["triage-stats", caseId] })
    queryClient.invalidateQueries({ queryKey: ["triage-classification", caseId] })
    queryClient.invalidateQueries({ queryKey: ["triage-profile", caseId] })
    queryClient.invalidateQueries({ queryKey: ["triage-files", caseId] })
    queryClient.invalidateQueries({ queryKey: ["triage-tasks", caseId] })
  }
}

function getStage(caseData: TriageCase | undefined, type: string) {
  return caseData?.stages?.find((stage) => stage.type === type)
}

function firstOpenStageIndex(stages: TriageStage[]) {
  const next = stages.findIndex((stage) => stage.status !== "completed")
  return next === -1 ? Math.max(0, stages.length - 1) : Math.max(0, next)
}

function statusBadge(status: string) {
  if (status === "completed" || status === "profiled" || status === "classified" || status === "scan_complete") {
    return "success"
  }
  if (status === "failed") return "danger"
  if (isRunningStatus(status)) return "info"
  if (status === "processing") return "amber"
  return "slate"
}

function StatusBadge({ status }: { status: string }) {
  const running = isRunningStatus(status)
  return (
    <Badge variant={statusBadge(status)} className="capitalize">
      {running ? <Loader2 className="animate-spin" /> : null}
      {status.replaceAll("_", " ")}
    </Badge>
  )
}

function StageIcon({ stage }: { stage: TriageStage }) {
  if (stage.status === "running") return <Loader2 className="size-4 animate-spin" />
  if (stage.status === "completed") return <CheckCircle2 className="size-4" />
  if (stage.status === "failed") return <AlertCircle className="size-4" />
  if (stage.type === "scan") return <HardDrive className="size-4" />
  if (stage.type === "classify") return <Shield className="size-4" />
  if (stage.type === "profile") return <BarChart3 className="size-4" />
  return <Layers className="size-4" />
}

function StatTile({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string | number
  icon?: React.ComponentType<{ className?: string }>
}) {
  return (
    <div className="rounded-md border border-border bg-muted/30 p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {Icon ? <Icon className="size-3.5" /> : null}
        {label}
      </div>
      <div className="mt-1 truncate text-xl font-semibold text-foreground">{value}</div>
    </div>
  )
}

function TriageCaseList({
  selectedId,
  onSelect,
}: {
  selectedId: string | null
  onSelect: (caseId: string) => void
}) {
  const [search, setSearch] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<TriageCase | null>(null)
  const queryClient = useQueryClient()

  const casesQuery = useQuery({
    queryKey: ["triage-cases"],
    queryFn: triageAPI.listCases,
    refetchInterval: (query) =>
      query.state.data?.some((item) => isRunningStatus(item.status, { includeProcessing: false })) ? 4000 : false,
  })

  const deleteMutation = useMutation({
    mutationFn: (caseId: string) => triageAPI.deleteCase(caseId),
    onSuccess: () => {
      toast.success("Triage case deleted")
      setDeleteTarget(null)
      invalidateTriage(queryClient)
    },
    onError: (error) => toast.error(error.message),
  })

  const filtered = useMemo(() => {
    const needle = search.toLowerCase()
    return (casesQuery.data ?? []).filter(
      (item) =>
        item.name.toLowerCase().includes(needle) ||
        item.description?.toLowerCase().includes(needle) ||
        item.source_path.toLowerCase().includes(needle)
    )
  }, [casesQuery.data, search])

  return (
    <div className="flex h-full flex-col border-r border-border">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <HardDrive className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">Evidence Triage</span>
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => casesQuery.refetch()}
          title="Refresh triage cases"
        >
          <RefreshCw className={cn("size-3.5", casesQuery.isFetching && "animate-spin")} />
        </Button>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="size-3.5" />
          New
        </Button>
      </div>

      <div className="border-b border-border p-3">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="h-8 pl-7 text-xs"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search triage cases..."
          />
        </div>
      </div>

      <ScrollArea className="flex-1">
        {casesQuery.isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={HardDrive}
            title="No triage cases"
            description={search ? "No matching source directories" : "Create a triage case to scan a mounted drive or directory"}
            className="py-10"
          />
        ) : (
          <div className="space-y-1 p-2">
            {filtered.map((item) => (
              <button
                key={item.id}
                onClick={() => onSelect(item.id)}
                className={cn(
                  "w-full rounded-md border p-3 text-left transition-colors",
                  selectedId === item.id
                    ? "border-amber-300 bg-amber-50/80 dark:border-amber-500/50 dark:bg-amber-500/10"
                    : "border-transparent hover:border-border hover:bg-muted/60"
                )}
              >
                <div className="flex items-start gap-2">
                  <HardDrive className="mt-0.5 size-4 shrink-0 text-amber-500" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold">{item.name}</span>
                      <StatusBadge status={item.status} />
                    </div>
                    {item.description ? (
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {item.description}
                      </p>
                    ) : null}
                    <p className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
                      {item.source_path}
                    </p>
                    <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span>{(item.scan_stats?.total_files ?? 0).toLocaleString()} files</span>
                      <span>{formatBytes(item.scan_stats?.total_size)}</span>
                      <span>{formatDateTime(item.created_at)}</span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="shrink-0 text-muted-foreground hover:text-red-500"
                    onClick={(event) => {
                      event.stopPropagation()
                      setDeleteTarget(item)
                    }}
                    title="Delete triage case"
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </button>
            ))}
          </div>
        )}
      </ScrollArea>

      <CreateTriageCaseDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(created) => onSelect(created.id)}
      />
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete triage case?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This removes the triage case metadata and its scanned triage graph data.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={deleteMutation.isPending}
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              {deleteMutation.isPending ? <LoadingSpinner size="sm" /> : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function CreateTriageCaseDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (created: TriageCase) => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [sourcePath, setSourcePath] = useState("")

  const createMutation = useMutation({
    mutationFn: () =>
      triageAPI.createCase({
        name: name.trim(),
        description: description.trim(),
        source_path: sourcePath.trim(),
      }),
    onSuccess: (created) => {
      toast.success("Triage case created")
      setName("")
      setDescription("")
      setSourcePath("")
      onOpenChange(false)
      invalidateTriage(queryClient)
      onCreated(created)
    },
    onError: (error) => toast.error(error.message),
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    createMutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>New Triage Case</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Name
            </label>
            <Input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Suspect laptop image"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Description
            </label>
            <Textarea
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional context for this mounted source..."
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Source Directory
            </label>
            <DirectoryBrowser value={sourcePath} onChange={setSourcePath} />
          </div>
          <DialogFooter>
            <Button variant="outline" type="button" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!name.trim() || !sourcePath.trim() || createMutation.isPending}
            >
              {createMutation.isPending ? <LoadingSpinner size="sm" /> : "Create and Open"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DirectoryBrowser({
  value,
  onChange,
}: {
  value: string
  onChange: (path: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [path, setPath] = useState(value || "/")

  const browseQuery = useQuery({
    queryKey: ["triage-browse", path],
    queryFn: () => triageAPI.browseDirectory(path),
    enabled: open,
    retry: false,
  })

  const entries = browseQuery.data?.entries ?? []
  const directories = entries.filter((entry) => entry.is_dir)
  const files = entries.filter((entry) => !entry.is_dir)

  return (
    <>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => {
            setPath(value || "/")
            setOpen(true)
          }}
          className={cn(
            "flex h-9 min-w-0 flex-1 items-center gap-2 rounded-md border px-3 text-left text-sm transition-colors",
            value
              ? "border-input bg-background hover:bg-muted/60"
              : "border-dashed border-input bg-muted/30 text-muted-foreground hover:bg-muted/60"
          )}
        >
          {value ? (
            <Folder className="size-4 shrink-0 text-amber-500" />
          ) : (
            <FolderOpen className="size-4 shrink-0" />
          )}
          <span className="truncate font-mono text-xs">
            {value || "Select a server directory..."}
          </span>
        </button>
        {value ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onChange("")}
            title="Clear directory"
          >
            <X className="size-4" />
          </Button>
        ) : null}
      </div>

      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (nextOpen) setPath(value || "/")
          setOpen(nextOpen)
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HardDrive className="size-4 text-amber-500" />
              Select Source Directory
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 p-2">
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={!browseQuery.data?.parent_path}
                onClick={() => browseQuery.data?.parent_path && setPath(browseQuery.data.parent_path)}
                title="Go up"
              >
                <ChevronUp className="size-4" />
              </Button>
              <Input
                value={path}
                onChange={(event) => setPath(event.target.value)}
                className="h-8 font-mono text-xs"
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    browseQuery.refetch()
                  }
                }}
              />
              <Button type="button" variant="outline" size="sm" onClick={() => browseQuery.refetch()}>
                Browse
              </Button>
            </div>

            <div className="h-[360px] overflow-hidden rounded-md border border-border">
              {browseQuery.isFetching ? (
                <div className="flex h-full items-center justify-center">
                  <LoadingSpinner />
                </div>
              ) : browseQuery.isError ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-sm text-muted-foreground">
                  <AlertCircle className="size-8 text-red-500" />
                  {(browseQuery.error as Error).message}
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="divide-y divide-border">
                    {directories.map((entry) => (
                      <DirectoryRow key={entry.path} entry={entry} onOpen={setPath} />
                    ))}
                    {files.slice(0, 40).map((entry) => (
                      <div
                        key={entry.path}
                        className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground opacity-60"
                      >
                        <File className="size-4 shrink-0" />
                        <span className="truncate">{entry.name}</span>
                      </div>
                    ))}
                    {entries.length === 0 ? (
                      <div className="px-3 py-10 text-center text-sm text-muted-foreground">
                        Empty directory
                      </div>
                    ) : null}
                  </div>
                </ScrollArea>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" type="button" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => {
                onChange(browseQuery.data?.current_path ?? path)
                setOpen(false)
              }}
              disabled={!browseQuery.data?.current_path}
            >
              <Check className="size-4" />
              Select Directory
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function DirectoryRow({
  entry,
  onOpen,
}: {
  entry: DirectoryEntry
  onOpen: (path: string) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(entry.path)}
      className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/60"
    >
      <Folder className="size-4 shrink-0 text-amber-500" />
      <span className="truncate">{entry.name}</span>
      <ChevronRight className="ml-auto size-4 shrink-0 text-muted-foreground" />
    </button>
  )
}

function StagePipeline({
  stages,
  activeStageId,
  onStageChange,
}: {
  stages: TriageStage[]
  activeStageId: string | null
  onStageChange: (stageId: string) => void
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-border bg-background px-4 py-2">
      {stages.map((stage, index) => (
        <div key={stage.id} className="flex items-center gap-1">
          {index > 0 ? <ChevronRight className="size-4 shrink-0 text-muted-foreground/50" /> : null}
          <button
            type="button"
            onClick={() => onStageChange(stage.id)}
            className={cn(
              "flex h-8 shrink-0 items-center gap-2 rounded-md border px-3 text-xs font-semibold transition-colors",
              activeStageId === stage.id
                ? "border-amber-400 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
                : stage.status === "completed"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
                  : stage.status === "failed"
                    ? "border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
                    : "border-border bg-muted/30 text-muted-foreground hover:bg-muted"
            )}
          >
            <StageIcon stage={stage} />
            <span>{stage.name}</span>
          </button>
        </div>
      ))}
    </div>
  )
}

function TriageWorkbench({
  caseId,
  onBack,
}: {
  caseId: string
  onBack: () => void
}) {
  const queryClient = useQueryClient()
  const [activeStageId, setActiveStageId] = useState<string | null>(null)
  const [stageBuilderOpen, setStageBuilderOpen] = useState(false)
  const [templateOpen, setTemplateOpen] = useState<"apply" | "save" | null>(null)
  const [ingestOpen, setIngestOpen] = useState(false)

  const caseQuery = useQuery({
    queryKey: ["triage-case", caseId],
    queryFn: () => triageAPI.getCase(caseId),
    refetchInterval: (query) =>
      query.state.data?.stages?.some((stage) => stage.status === "running") ||
      isRunningStatus(query.state.data?.status, { includeProcessing: false })
        ? 3000
        : false,
  })

  const tasksQuery = useQuery({
    queryKey: ["triage-tasks", caseId],
    queryFn: () => triageAPI.listTasks(caseId),
    refetchInterval: 5000,
  })

  const caseData = caseQuery.data
  const stages = useMemo(() => caseData?.stages ?? [], [caseData?.stages])

  const effectiveStageId = stages.some((stage) => stage.id === activeStageId)
    ? activeStageId
    : stages[firstOpenStageIndex(stages)]?.id
  const activeStage = stages.find((stage) => stage.id === effectiveStageId) ?? stages[0]
  const hasCustomStages = stages.some((stage) => stage.type === "custom")

  if (caseQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!caseData) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState title="Triage case unavailable" description="The case may have been deleted." />
      </div>
    )
  }

  return (
    <div className="relative flex h-full min-w-0 flex-col">
      <div className="flex h-14 items-center gap-3 border-b border-border px-4">
        <Button variant="ghost" size="icon" onClick={onBack} title="Back to triage list">
          <ArrowLeft className="size-4" />
        </Button>
        <HardDrive className="size-5 text-amber-500" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-sm font-semibold">{caseData.name}</h1>
            <StatusBadge status={caseData.status} />
          </div>
          <p className="truncate font-mono text-[11px] text-muted-foreground">
            {caseData.source_path}
          </p>
        </div>
        <div className="hidden items-center gap-3 text-xs text-muted-foreground md:flex">
          <span>{(caseData.scan_stats?.total_files ?? 0).toLocaleString()} files</span>
          <span>{formatBytes(caseData.scan_stats?.total_size)}</span>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled
          title={TRIAGE_INGEST_DISABLED_MESSAGE}
        >
          <FolderInput className="size-3.5" />
          Ingest
        </Button>
        <Button variant="outline" size="sm" onClick={() => setTemplateOpen("apply")}>
          <BookTemplate className="size-3.5" />
          Templates
        </Button>
        {hasCustomStages ? (
          <Button variant="outline" size="sm" onClick={() => setTemplateOpen("save")}>
            <Save className="size-3.5" />
            Save
          </Button>
        ) : null}
        <Button size="sm" onClick={() => setStageBuilderOpen(true)}>
          <Plus className="size-3.5" />
          Stage
        </Button>
      </div>

      <StagePipeline
        stages={stages}
        activeStageId={effectiveStageId ?? null}
        onStageChange={setActiveStageId}
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px]">
        <ScrollArea className="min-h-0 border-r border-border bg-muted/20">
          <div className="p-4">
            <StagePanel
              caseData={caseData}
              activeStage={activeStage}
              onRefresh={() => invalidateTriage(queryClient, caseId)}
            />
          </div>
        </ScrollArea>
        <div className="min-h-0">
          <Tabs defaultValue="files" className="h-full gap-0">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <TabsList className="h-8">
                <TabsTrigger value="files" className="text-xs">
                  <FileSearch className="size-3.5" />
                  Files
                </TabsTrigger>
                <TabsTrigger value="activity" className="text-xs">
                  <RefreshCw className="size-3.5" />
                  Activity
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="files" className="min-h-0">
              <FileListPanel caseId={caseId} />
            </TabsContent>
            <TabsContent value="activity" className="min-h-0">
              <ActivityPanel tasks={tasksQuery.data ?? []} loading={tasksQuery.isLoading} />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <TriageAdvisor caseId={caseId} onAction={() => setStageBuilderOpen(true)} />

      <StageBuilderDialog
        caseId={caseId}
        open={stageBuilderOpen}
        onOpenChange={setStageBuilderOpen}
      />
      <TemplateDialog
        mode={templateOpen}
        caseId={caseId}
        onOpenChange={(open) => !open && setTemplateOpen(null)}
      />
      <IngestDialog
        open={ingestOpen}
        onOpenChange={setIngestOpen}
        triageCase={caseData}
      />
    </div>
  )
}

function StagePanel({
  caseData,
  activeStage,
  onRefresh,
}: {
  caseData: TriageCase
  activeStage?: TriageStage
  onRefresh: () => void
}) {
  if (!activeStage) {
    return <EmptyState title="No stages" description="This triage case has no processing stages." />
  }
  if (activeStage.type === "scan") {
    return <ScanStage caseData={caseData} stage={activeStage} onRefresh={onRefresh} />
  }
  if (activeStage.type === "classify") {
    return <ClassificationStage caseData={caseData} stage={activeStage} onRefresh={onRefresh} />
  }
  if (activeStage.type === "profile") {
    return <ProfileStage caseData={caseData} stage={activeStage} onRefresh={onRefresh} />
  }
  return <CustomStage caseData={caseData} stage={activeStage} onRefresh={onRefresh} />
}

function StageShell({
  title,
  description,
  stage,
  icon: Icon,
  action,
  children,
}: {
  title: string
  description: string
  stage: TriageStage
  icon: React.ComponentType<{ className?: string }>
  action?: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="rounded-md border border-border bg-muted p-2">
              {stage.status === "running" ? (
                <Loader2 className="size-5 animate-spin text-blue-500" />
              ) : stage.status === "completed" ? (
                <CheckCircle2 className="size-5 text-emerald-500" />
              ) : stage.status === "failed" ? (
                <AlertCircle className="size-5 text-red-500" />
              ) : (
                <Icon className="size-5 text-muted-foreground" />
              )}
            </div>
            <div className="min-w-0">
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </div>
          </div>
          <CardAction>{action}</CardAction>
        </CardHeader>
        <CardContent className="space-y-4">
          {stage.error ? (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              {stage.error}
            </div>
          ) : null}
          {stage.status === "running" ? (
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Progress</span>
                <span>
                  {(stage.files_processed ?? 0).toLocaleString()}
                  {stage.files_total ? ` / ${stage.files_total.toLocaleString()}` : ""}
                </span>
              </div>
              <Progress value={stageProgress(stage) || 100} />
            </div>
          ) : null}
          {children}
        </CardContent>
      </Card>
    </div>
  )
}

function ScanStage({
  caseData,
  stage,
  onRefresh,
}: {
  caseData: TriageCase
  stage: TriageStage
  onRefresh: () => void
}) {
  const queryClient = useQueryClient()
  const statsQuery = useQuery({
    queryKey: ["triage-stats", caseData.id],
    queryFn: () => triageAPI.getStats(caseData.id),
    enabled: stage.status === "completed" || stage.status === "running",
    refetchInterval: stage.status === "running" ? 3000 : false,
  })
  const scanMutation = useMutation({
    mutationFn: (resume: boolean) => triageAPI.startScan(caseData.id, resume),
    onSuccess: () => {
      toast.success("Scan started")
      invalidateTriage(queryClient, caseData.id)
      onRefresh()
    },
    onError: (error) => toast.error(error.message),
  })

  const displayStats = { ...caseData.scan_stats, ...statsQuery.data } as Partial<ScanStats>
  const totalFiles = displayStats.total_files ?? stage.files_processed ?? 0
  const categories = displayStats.by_category ?? {}

  return (
    <StageShell
      title={stage.status === "completed" ? "Scan Complete" : stage.status === "running" ? "Scanning Source" : "Ready to Scan"}
      description={caseData.source_path}
      stage={stage}
      icon={HardDrive}
      action={
        stage.status === "pending" || stage.status === "failed" ? (
          <Button
            onClick={() => scanMutation.mutate(stage.status === "failed")}
            disabled={scanMutation.isPending}
          >
            {scanMutation.isPending ? (
              <LoadingSpinner size="sm" />
            ) : stage.status === "failed" ? (
              <RotateCcw className="size-4" />
            ) : (
              <Play className="size-4" />
            )}
            {stage.status === "failed" ? "Resume Scan" : "Start Scan"}
          </Button>
        ) : null
      }
    >
      <div className="grid gap-3 sm:grid-cols-4">
        <StatTile label="Files" value={totalFiles.toLocaleString()} icon={FileText} />
        <StatTile label="Size" value={formatBytes(displayStats.total_size)} icon={Database} />
        <StatTile label="Unique Hashes" value={(displayStats.unique_hashes ?? 0).toLocaleString()} icon={Shield} />
        <StatTile label="OS" value={displayStats.os_detected ?? "Unknown"} icon={HardDrive} />
      </div>
      {totalFiles > 0 ? <CategoryBreakdown categories={categories} total={totalFiles} /> : null}
    </StageShell>
  )
}

function CategoryBreakdown({
  categories,
  total,
}: {
  categories: Record<string, number>
  total: number
}) {
  const entries = Object.entries(categories).sort(([, a], [, b]) => b - a)
  if (!entries.length) return null
  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle>File Categories</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex h-3 overflow-hidden rounded-full bg-muted">
          {entries.map(([category, count]) => {
            const percent = (count / total) * 100
            if (percent < 0.5) return null
            return (
              <div
                key={category}
                className={cn("h-full", CATEGORY_COLORS[category] ?? CATEGORY_COLORS.other)}
                style={{ width: `${percent}%` }}
                title={`${category}: ${count.toLocaleString()}`}
              />
            )
          })}
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {entries.map(([category, count]) => (
            <div key={category} className="flex items-center gap-2 text-xs">
              <span className={cn("size-2.5 rounded-sm", CATEGORY_COLORS[category] ?? CATEGORY_COLORS.other)} />
              <span className="capitalize">{category}</span>
              <span className="ml-auto text-muted-foreground">{count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function ClassificationStage({
  caseData,
  stage,
  onRefresh,
}: {
  caseData: TriageCase
  stage: TriageStage
  onRefresh: () => void
}) {
  const queryClient = useQueryClient()
  const [hashUploadOpen, setHashUploadOpen] = useState(false)
  const classifyQuery = useQuery({
    queryKey: ["triage-classification", caseData.id],
    queryFn: () => triageAPI.getClassification(caseData.id),
    enabled: stage.status === "completed" || stage.status === "running",
    refetchInterval: stage.status === "running" ? 3000 : false,
  })
  const classifyMutation = useMutation({
    mutationFn: () => triageAPI.startClassification(caseData.id),
    onSuccess: () => {
      toast.success("Classification started")
      invalidateTriage(queryClient, caseData.id)
      onRefresh()
    },
    onError: (error) => toast.error(error.message),
  })

  const scanComplete = getStage(caseData, "scan")?.status === "completed"
  const stats = classifyQuery.data

  return (
    <StageShell
      title={stage.status === "completed" ? "Classification Complete" : stage.status === "running" ? "Classifying Files" : "Ready to Classify"}
      description={scanComplete ? "Hash lookup and path analysis are available." : "Complete scan before classification."}
      stage={stage}
      icon={Shield}
      action={
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setHashUploadOpen((open) => !open)}>
            <Upload className="size-4" />
            Hash Set
          </Button>
          {(stage.status === "pending" || stage.status === "failed") && scanComplete ? (
            <Button onClick={() => classifyMutation.mutate()} disabled={classifyMutation.isPending}>
              {classifyMutation.isPending ? <LoadingSpinner size="sm" /> : <Play className="size-4" />}
              {stage.status === "failed" ? "Retry" : "Classify"}
            </Button>
          ) : null}
        </div>
      }
    >
      {hashUploadOpen ? <HashSetUpload caseId={caseData.id} onUploaded={() => setHashUploadOpen(false)} /> : null}
      <ClassificationSummary stats={stats} />
    </StageShell>
  )
}

function ClassificationSummary({ stats }: { stats?: ClassificationStats }) {
  const labels = [
    ["Known Good", stats?.known_good ?? 0, "bg-emerald-500"],
    ["Known Bad", stats?.known_bad ?? 0, "bg-red-500"],
    ["Suspicious", stats?.suspicious ?? 0, "bg-amber-500"],
    ["Custom Match", stats?.custom_match ?? 0, "bg-cyan-500"],
    ["Unknown", stats?.unknown ?? 0, "bg-slate-400"],
  ] as const
  const total = Math.max(1, labels.reduce((sum, [, count]) => sum + count, 0))
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <StatTile label="Classified" value={(stats?.total_classified ?? 0).toLocaleString()} icon={Shield} />
        <StatTile label="System Files" value={(stats?.system_files ?? 0).toLocaleString()} icon={Database} />
        <StatTile label="User Files" value={(stats?.user_files ?? 0).toLocaleString()} icon={Users} />
        <StatTile label="Users" value={(stats?.user_accounts ?? []).length} icon={FolderOpen} />
      </div>
      <Card className="shadow-none">
        <CardHeader>
          <CardTitle>Hash Classification</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {labels.map(([label, count, color]) => (
            <div key={label} className="grid grid-cols-[120px_minmax(0,1fr)_70px] items-center gap-3 text-xs">
              <span className="text-muted-foreground">{label}</span>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className={cn("h-full rounded-full", color)} style={{ width: `${(count / total) * 100}%` }} />
              </div>
              <span className="text-right tabular-nums">{count.toLocaleString()}</span>
            </div>
          ))}
        </CardContent>
      </Card>
      {stats?.user_accounts?.length ? (
        <div className="flex flex-wrap gap-1.5">
          {stats.user_accounts.map((account) => (
            <Badge key={account} variant="outline">
              <FolderOpen className="size-3" />
              {account}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function HashSetUpload({ caseId, onUploaded }: { caseId: string; onUploaded: () => void }) {
  const [name, setName] = useState("")
  const [hashText, setHashText] = useState("")
  const mutation = useMutation({
    mutationFn: () =>
      triageAPI.uploadHashSet(caseId, {
        name: name.trim(),
        hashes: hashText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean),
      }),
    onSuccess: (result) => {
      toast.success(`Uploaded ${result.valid_hashes.toLocaleString()} valid hashes`)
      onUploaded()
    },
    onError: (error) => toast.error(error.message),
  })
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3">
      <div className="grid gap-2">
        <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Hash set name" />
        <Textarea
          value={hashText}
          onChange={(event) => setHashText(event.target.value)}
          placeholder="Paste SHA-256 hashes, one per line"
          rows={5}
          className="font-mono text-xs"
        />
        <div className="flex justify-end">
          <Button disabled={!name.trim() || !hashText.trim() || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? <LoadingSpinner size="sm" /> : <Upload className="size-4" />}
            Upload
          </Button>
        </div>
      </div>
    </div>
  )
}

function ProfileStage({
  caseData,
  stage,
  onRefresh,
}: {
  caseData: TriageCase
  stage: TriageStage
  onRefresh: () => void
}) {
  const queryClient = useQueryClient()
  const profileQuery = useQuery({
    queryKey: ["triage-profile", caseData.id],
    queryFn: () => triageAPI.getProfile(caseData.id),
    enabled: stage.status === "completed" || stage.status === "running",
    refetchInterval: stage.status === "running" ? 3000 : false,
  })
  const generateMutation = useMutation({
    mutationFn: () => triageAPI.generateProfile(caseData.id),
    onSuccess: () => {
      toast.success("Profile generation started")
      invalidateTriage(queryClient, caseData.id)
      onRefresh()
    },
    onError: (error) => toast.error(error.message),
  })
  const scanComplete = getStage(caseData, "scan")?.status === "completed"
  const rawProfile = profileQuery.data
  const profile =
    rawProfile && !("message" in rawProfile) ? (rawProfile as TriageProfile) : caseData.profile

  return (
    <StageShell
      title={stage.status === "completed" ? "Triage Dashboard" : stage.status === "running" ? "Generating Profile" : "Ready to Profile"}
      description={scanComplete ? "Build profile, artifact, timeline, mismatch and user views." : "Complete scan before profiling."}
      stage={stage}
      icon={BarChart3}
      action={
        (stage.status === "pending" || stage.status === "failed") && scanComplete ? (
          <Button onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending}>
            {generateMutation.isPending ? <LoadingSpinner size="sm" /> : <Play className="size-4" />}
            {stage.status === "failed" ? "Retry" : "Generate"}
          </Button>
        ) : null
      }
    >
      {profile ? <ProfileDashboard caseId={caseData.id} profile={profile} /> : null}
    </StageShell>
  )
}

function ProfileDashboard({ caseId, profile }: { caseId: string; profile: TriageProfile }) {
  const timelineQuery = useQuery({
    queryKey: ["triage-timeline", caseId],
    queryFn: () => triageAPI.getTimeline(caseId),
  })
  const artifactsQuery = useQuery({
    queryKey: ["triage-artifacts", caseId],
    queryFn: () => triageAPI.getArtifacts(caseId),
  })
  const mismatchesQuery = useQuery({
    queryKey: ["triage-mismatches", caseId],
    queryFn: () => triageAPI.getMismatches(caseId),
  })
  const categoryRows = normalizeCategoryRows(profile.by_category)
  const cls = profile.classification ?? {}

  return (
    <Tabs defaultValue="overview">
      <TabsList className="w-full justify-start overflow-x-auto">
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="categories">File Types</TabsTrigger>
        <TabsTrigger value="timeline">Timeline</TabsTrigger>
        <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
        <TabsTrigger value="mismatches">Mismatches</TabsTrigger>
        <TabsTrigger value="users">Users</TabsTrigger>
      </TabsList>
      <TabsContent value="overview" className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-4">
          <StatTile label="Files" value={(profile.total_files ?? 0).toLocaleString()} icon={HardDrive} />
          <StatTile label="Size" value={formatBytes(profile.total_size)} icon={Database} />
          <StatTile label="OS" value={profile.os_detected ?? "Unknown"} icon={FolderOpen} />
          <StatTile label="User Accounts" value={cls.user_accounts?.length ?? 0} icon={Users} />
        </div>
        <ClassificationSummary stats={cls as ClassificationStats} />
      </TabsContent>
      <TabsContent value="categories">
        <div className="space-y-2">
          {categoryRows.map((row) => (
            <div key={row.category} className="rounded-md border border-border bg-background p-3">
              <div className="flex items-center gap-2">
                <span className={cn("size-2.5 rounded-sm", CATEGORY_COLORS[row.category] ?? CATEGORY_COLORS.other)} />
                <span className="font-medium capitalize">{row.category}</span>
                <span className="ml-auto text-sm text-muted-foreground">
                  {row.count.toLocaleString()} files {row.total_size ? `(${formatBytes(row.total_size)})` : ""}
                </span>
              </div>
              {row.top_extensions.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {row.top_extensions.map((extension) => (
                    <Badge key={extension} variant="outline" className="font-mono">
                      {extension || "(none)"}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </TabsContent>
      <TabsContent value="timeline">
        <SimpleRecords
          loading={timelineQuery.isLoading}
          records={timelineQuery.data ?? []}
          empty="No timeline data available"
        />
      </TabsContent>
      <TabsContent value="artifacts">
        <ArtifactList
          loading={artifactsQuery.isLoading}
          artifacts={artifactsQuery.data ?? []}
          empty="No high-value artifacts detected"
        />
      </TabsContent>
      <TabsContent value="mismatches">
        <SimpleRecords
          loading={mismatchesQuery.isLoading}
          records={mismatchesQuery.data ?? []}
          empty="No extension mismatches detected"
        />
      </TabsContent>
      <TabsContent value="users">
        <SimpleRecords
          records={profile.user_profiles ?? []}
          empty="No user profiles detected"
        />
      </TabsContent>
    </Tabs>
  )
}

function SimpleRecords({
  loading,
  records,
  empty,
}: {
  loading?: boolean
  records: Array<Record<string, unknown>>
  empty: string
}) {
  if (loading) return <LoadingSpinner />
  if (!records.length) return <EmptyState title={empty} className="py-8" />
  return (
    <div className="space-y-2">
      {records.slice(0, 50).map((record, index) => (
        <div key={index} className="rounded-md border border-border bg-background p-3 text-xs">
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-muted-foreground">
            {JSON.stringify(record, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  )
}

function ArtifactList({
  loading,
  artifacts,
  empty,
}: {
  loading?: boolean
  artifacts: Artifact[]
  empty: string
}) {
  if (loading) return <LoadingSpinner />
  if (!artifacts.length) return <EmptyState title={empty} className="py-8" />
  return (
    <div className="space-y-2">
      {artifacts.map((artifact) => (
        <div key={artifact.id} className="rounded-md border border-border bg-background p-3">
          <div className="flex items-center gap-2">
            <FileText className="size-4 text-amber-500" />
            <span className="truncate text-sm font-medium">
              {artifact.source_file_path ?? artifact.source_path ?? artifact.artifact_type}
            </span>
            <Badge variant="outline">{artifact.artifact_type}</Badge>
          </div>
          {artifact.content ? (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs text-muted-foreground">
              {artifact.content.slice(0, 2000)}
            </pre>
          ) : null}
        </div>
      ))}
    </div>
  )
}

function CustomStage({
  caseData,
  stage,
  onRefresh,
}: {
  caseData: TriageCase
  stage: TriageStage
  onRefresh: () => void
}) {
  const queryClient = useQueryClient()
  const resultsQuery = useQuery({
    queryKey: ["triage-stage-results", caseData.id, stage.id],
    queryFn: () => triageAPI.getStageResults(caseData.id, stage.id),
    enabled: stage.status === "completed" || stage.status === "running",
    refetchInterval: stage.status === "running" ? 5000 : false,
  })
  const executeMutation = useMutation({
    mutationFn: () => triageAPI.executeStage(caseData.id, stage.id),
    onSuccess: () => {
      toast.success("Stage execution started")
      invalidateTriage(queryClient, caseData.id)
      onRefresh()
    },
    onError: (error) => toast.error(error.message),
  })
  const config = stage.config ?? {}
  const fileFilter = (config.file_filter ?? {}) as Record<string, unknown>
  return (
    <StageShell
      title={stage.name}
      description={`Processor: ${String(config.processor_name ?? "unknown")}`}
      stage={stage}
      icon={Layers}
      action={
        stage.status === "pending" || stage.status === "failed" ? (
          <Button onClick={() => executeMutation.mutate()} disabled={executeMutation.isPending}>
            {executeMutation.isPending ? <LoadingSpinner size="sm" /> : <Play className="size-4" />}
            {stage.status === "failed" ? "Retry" : "Execute"}
          </Button>
        ) : null
      }
    >
      {Object.keys(fileFilter).length ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Filter className="size-3.5 text-muted-foreground" />
          {Object.entries(fileFilter).map(([key, value]) => (
            <Badge key={key} variant="outline">
              {key}: {String(value)}
            </Badge>
          ))}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="Total" value={(stage.files_total ?? 0).toLocaleString()} />
        <StatTile label="Processed" value={(stage.files_processed ?? 0).toLocaleString()} />
        <StatTile label="Failed" value={(stage.files_failed ?? 0).toLocaleString()} />
      </div>
      {(stage.status === "completed" || stage.status === "running") ? (
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Artifacts</CardTitle>
          </CardHeader>
          <CardContent>
            <ArtifactList
              loading={resultsQuery.isLoading}
              artifacts={resultsQuery.data ?? []}
              empty="No artifacts produced"
            />
          </CardContent>
        </Card>
      ) : null}
    </StageShell>
  )
}

function FileListPanel({ caseId }: { caseId: string }) {
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("all")
  const [classification, setClassification] = useState("all")
  const [userOnly, setUserOnly] = useState(false)
  const [page, setPage] = useState(0)
  const limit = 50
  const params: TriageFileListParams = {
    skip: page * limit,
    limit,
    sort_by: "relative_path",
    sort_dir: "asc",
    search,
    category: category === "all" ? undefined : category,
    hash_classification: classification === "all" ? undefined : classification,
    is_user_file: userOnly ? true : undefined,
  }
  const filesQuery = useQuery({
    queryKey: ["triage-files", caseId, params],
    queryFn: () => triageAPI.getFiles(caseId, params),
  })
  const files = filesQuery.data?.files ?? []
  const total = filesQuery.data?.total ?? 0
  const maxPage = Math.max(0, Math.ceil(total / limit) - 1)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-border p-3">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPage(0)
            }}
            className="h-8 pl-7 text-xs"
            placeholder="Filter filenames..."
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Select value={category} onValueChange={(value) => { setCategory(value); setPage(0) }}>
            <SelectTrigger className="h-8 w-full text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {CATEGORIES.map((item) => (
                <SelectItem key={item} value={item}>{item}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={classification} onValueChange={(value) => { setClassification(value); setPage(0) }}>
            <SelectTrigger className="h-8 w-full text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All hash states</SelectItem>
              {["known_good", "known_bad", "suspicious", "custom_match", "unknown"].map((item) => (
                <SelectItem key={item} value={item}>{item.replaceAll("_", " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch size="sm" checked={userOnly} onCheckedChange={setUserOnly} />
          User files only
        </label>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        {filesQuery.isLoading ? (
          <div className="flex justify-center py-8"><LoadingSpinner /></div>
        ) : files.length === 0 ? (
          <EmptyState title="No files found" description="Run scan or adjust filters." className="py-10" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead className="w-20">Size</TableHead>
                <TableHead className="w-24">Class</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {files.map((file) => (
                <FileRow key={file.relative_path} file={file} />
              ))}
            </TableBody>
          </Table>
        )}
      </ScrollArea>
      <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted-foreground">
        <span>{total.toLocaleString()} files</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
            Prev
          </Button>
          <span>{page + 1} / {maxPage + 1}</span>
          <Button variant="outline" size="sm" disabled={page >= maxPage} onClick={() => setPage((p) => Math.min(maxPage, p + 1))}>
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}

function FileRow({ file }: { file: TriageFile }) {
  return (
    <TableRow>
      <TableCell className="max-w-[230px]">
        <div className="flex items-center gap-2">
          <FileText className="size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="truncate text-xs font-medium">{file.filename || file.relative_path}</p>
            <p className="truncate font-mono text-[10px] text-muted-foreground">{file.relative_path}</p>
          </div>
        </div>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">{formatBytes(file.size)}</TableCell>
      <TableCell>
        {file.hash_classification ? (
          <Badge variant={file.hash_classification === "known_bad" ? "danger" : file.hash_classification === "known_good" ? "success" : "slate"}>
            {file.hash_classification.replaceAll("_", " ")}
          </Badge>
        ) : (
          <Badge variant="outline">unclassified</Badge>
        )}
        {file.extension_mismatch ? <Badge variant="warning" className="mt-1">mismatch</Badge> : null}
      </TableCell>
    </TableRow>
  )
}

function ActivityPanel({
  tasks,
  loading,
}: {
  tasks: Array<{ id: string; task_name: string; status: string; progress?: Record<string, unknown>; error?: string | null; created_at: string }>
  loading: boolean
}) {
  if (loading) return <div className="flex justify-center py-8"><LoadingSpinner /></div>
  if (!tasks.length) return <EmptyState title="No triage activity" className="py-10" />
  return (
    <ScrollArea className="h-full">
      <div className="space-y-2 p-3">
        {tasks.map((task) => {
          const total = Number(task.progress?.total ?? task.progress?.progress_total ?? 0)
          const completed = Number(task.progress?.completed ?? task.progress?.progress_completed ?? 0)
          const progress = total ? Math.round((completed / total) * 100) : isRunningStatus(task.status) ? 100 : 0
          return (
            <div key={task.id} className="rounded-md border border-border bg-background p-3">
              <div className="flex items-center gap-2">
                <RefreshCw className={cn("size-3.5 text-muted-foreground", isRunningStatus(task.status) && "animate-spin")} />
                <span className="min-w-0 flex-1 truncate text-xs font-medium">{task.task_name}</span>
                <StatusBadge status={task.status} />
              </div>
              <Progress className="mt-2" value={progress} />
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>{formatDateTime(task.created_at)}</span>
                {total ? <span>{completed.toLocaleString()} / {total.toLocaleString()}</span> : null}
              </div>
              {task.error ? <p className="mt-2 text-xs text-red-500">{task.error}</p> : null}
            </div>
          )
        })}
      </div>
    </ScrollArea>
  )
}

function StageBuilderDialog({
  caseId,
  open,
  onOpenChange,
}: {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [selectedProcessor, setSelectedProcessor] = useState<ProcessorInfo | null>(null)
  const [stageName, setStageName] = useState("")
  const [category, setCategory] = useState("all")
  const [extension, setExtension] = useState("")
  const [pathPrefix, setPathPrefix] = useState("")
  const [userOnly, setUserOnly] = useState(false)

  const processorsQuery = useQuery({
    queryKey: ["triage-processors"],
    queryFn: triageAPI.listProcessors,
    enabled: open,
  })
  const createMutation = useMutation({
    mutationFn: () => {
      const fileFilter: Record<string, unknown> = {}
      if (category !== "all") fileFilter.category = category
      if (extension.trim()) fileFilter.extension = extension.trim()
      if (pathPrefix.trim()) fileFilter.path_prefix = pathPrefix.trim()
      if (userOnly) fileFilter.is_user_file = true
      return triageAPI.createStage(caseId, {
        name: stageName.trim(),
        processor_name: selectedProcessor?.name ?? "",
        config: {},
        file_filter: fileFilter,
      })
    },
    onSuccess: () => {
      toast.success("Processing stage created")
      invalidateTriage(queryClient, caseId)
      onOpenChange(false)
      setSelectedProcessor(null)
      setStageName("")
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create Processing Stage</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Stage Name</label>
            <Input value={stageName} onChange={(event) => setStageName(event.target.value)} placeholder="Extract PDF text" />
          </div>
          <div>
            <label className="mb-2 block text-xs font-medium text-muted-foreground">Processor</label>
            <div className="max-h-64 space-y-2 overflow-auto rounded-md border border-border p-2">
              {processorsQuery.isLoading ? <LoadingSpinner /> : null}
              {(processorsQuery.data ?? []).map((processor) => (
                <button
                  type="button"
                  key={processor.name}
                  onClick={() => {
                    setSelectedProcessor(processor)
                    if (!stageName) setStageName(processor.display_name)
                  }}
                  className={cn(
                    "w-full rounded-md border p-3 text-left transition-colors",
                    selectedProcessor?.name === processor.name
                      ? "border-amber-300 bg-amber-50 dark:bg-amber-500/10"
                      : "border-border hover:bg-muted/50"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Cpu className="size-4 text-amber-500" />
                    <span className="text-sm font-semibold">{processor.display_name}</span>
                    {processor.requires_llm ? <Badge variant="info">LLM</Badge> : null}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{processor.description}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {processor.input_types.map((type) => (
                      <Badge key={type} variant="outline">{type}</Badge>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {CATEGORIES.map((item) => (
                  <SelectItem key={item} value={item}>{item}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input value={extension} onChange={(event) => setExtension(event.target.value)} placeholder="Extension, e.g. .pdf" />
            <Input className="sm:col-span-2" value={pathPrefix} onChange={(event) => setPathPrefix(event.target.value)} placeholder="Path prefix, e.g. Users/jane/" />
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox checked={userOnly} onCheckedChange={(checked) => setUserOnly(checked === true)} />
              User files only
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!selectedProcessor || !stageName.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>
            {createMutation.isPending ? <LoadingSpinner size="sm" /> : <Plus className="size-4" />}
            Create Stage
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TemplateDialog({
  mode,
  caseId,
  onOpenChange,
}: {
  mode: "apply" | "save" | null
  caseId: string
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const templatesQuery = useQuery({
    queryKey: ["triage-templates"],
    queryFn: triageAPI.listTemplates,
    enabled: mode === "apply",
  })
  const saveMutation = useMutation({
    mutationFn: () => triageAPI.createTemplate(caseId, { name: name.trim(), description: description.trim() }),
    onSuccess: () => {
      toast.success("Template saved")
      queryClient.invalidateQueries({ queryKey: ["triage-templates"] })
      onOpenChange(false)
      setName("")
      setDescription("")
    },
    onError: (error) => toast.error(error.message),
  })
  const applyMutation = useMutation({
    mutationFn: (templateId: string) => triageAPI.applyTemplate(caseId, templateId),
    onSuccess: () => {
      toast.success("Template applied")
      invalidateTriage(queryClient, caseId)
      onOpenChange(false)
    },
    onError: (error) => toast.error(error.message),
  })
  const deleteMutation = useMutation({
    mutationFn: (templateId: string) => triageAPI.deleteTemplate(templateId),
    onSuccess: () => {
      toast.success("Template deleted")
      queryClient.invalidateQueries({ queryKey: ["triage-templates"] })
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <Dialog open={!!mode} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "save" ? "Save Workflow Template" : "Apply Workflow Template"}</DialogTitle>
        </DialogHeader>
        {mode === "save" ? (
          <div className="space-y-3">
            <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Template name" />
            <Textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Template description" />
          </div>
        ) : (
          <TemplateList
            loading={templatesQuery.isLoading}
            templates={templatesQuery.data ?? []}
            applyingId={applyMutation.variables}
            deletingId={deleteMutation.variables}
            onApply={(templateId) => applyMutation.mutate(templateId)}
            onDelete={(templateId) => deleteMutation.mutate(templateId)}
          />
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          {mode === "save" ? (
            <Button disabled={!name.trim() || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
              {saveMutation.isPending ? <LoadingSpinner size="sm" /> : <Save className="size-4" />}
              Save Template
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TemplateList({
  loading,
  templates,
  applyingId,
  deletingId,
  onApply,
  onDelete,
}: {
  loading: boolean
  templates: TriageTemplate[]
  applyingId?: string
  deletingId?: string
  onApply: (id: string) => void
  onDelete: (id: string) => void
}) {
  if (loading) return <LoadingSpinner />
  if (!templates.length) return <EmptyState title="No templates saved" className="py-8" />
  return (
    <div className="max-h-96 space-y-2 overflow-auto">
      {templates.map((template) => (
        <div key={template.id} className="rounded-md border border-border p-3">
          <div className="flex items-start gap-2">
            <BookTemplate className="mt-0.5 size-4 text-amber-500" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{template.name}</p>
              {template.description ? <p className="text-xs text-muted-foreground">{template.description}</p> : null}
              <p className="mt-1 text-[11px] text-muted-foreground">
                {template.stage_count} stage{template.stage_count === 1 ? "" : "s"} saved {formatDateTime(template.created_at)}
              </p>
            </div>
            <Button size="sm" disabled={applyingId === template.id} onClick={() => onApply(template.id)}>
              {applyingId === template.id ? <LoadingSpinner size="sm" /> : <Check className="size-3.5" />}
              Apply
            </Button>
            <Button variant="ghost" size="icon-sm" disabled={deletingId === template.id} onClick={() => onDelete(template.id)}>
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}

function TriageAdvisor({
  caseId,
  onAction,
}: {
  caseId: string
  onAction: (suggestion: AdvisorSuggestion) => void
}) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Array<{ role: "user" | "advisor"; content: string }>>([])
  const [input, setInput] = useState("")
  const suggestionsQuery = useQuery({
    queryKey: ["triage-advisor-suggestions", caseId],
    queryFn: () => triageAPI.advisorSuggest(caseId),
    enabled: open,
  })
  const chatMutation = useMutation({
    mutationFn: (question: string) => triageAPI.advisorChat(caseId, { question }),
    onSuccess: (result) => {
      setMessages((prev) => [...prev, { role: "advisor", content: result.answer || "No response." }])
    },
    onError: (error) => {
      setMessages((prev) => [...prev, { role: "advisor", content: error.message }])
    },
  })
  const send = () => {
    const question = input.trim()
    if (!question) return
    setMessages((prev) => [...prev, { role: "user", content: question }])
    setInput("")
    chatMutation.mutate(question)
  }

  if (!open) {
    return (
      <Button className="absolute bottom-4 right-4 shadow-lg" onClick={() => setOpen(true)}>
        <Sparkles className="size-4" />
        Advisor
      </Button>
    )
  }

  return (
    <div className="absolute bottom-4 right-4 z-20 flex max-h-[620px] w-[380px] flex-col overflow-hidden rounded-lg border border-border bg-background shadow-2xl">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Sparkles className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">Triage Advisor</span>
        <Button className="ml-auto" variant="ghost" size="icon-sm" onClick={() => setOpen(false)}>
          <X className="size-4" />
        </Button>
      </div>
      <ScrollArea className="max-h-48 border-b border-border bg-muted/30">
        <div className="space-y-2 p-3">
          {suggestionsQuery.isLoading ? <LoadingSpinner size="sm" /> : null}
          {(suggestionsQuery.data ?? []).map((suggestion, index) => (
            <div key={index} className="rounded-md border border-border bg-background p-2 text-xs">
              <div className="flex items-start gap-2">
                <Badge variant={suggestion.priority === "high" ? "danger" : suggestion.priority === "low" ? "info" : "warning"}>
                  {suggestion.priority ?? "medium"}
                </Badge>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{suggestion.action ?? "Suggested action"}</p>
                  <p className="mt-1 text-muted-foreground">{suggestion.detail ?? ""}</p>
                </div>
                {suggestion.processor || suggestion.stage_type ? (
                  <Button size="sm" variant="outline" onClick={() => onAction(suggestion)}>
                    Act
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
      <ScrollArea className="min-h-[180px] flex-1">
        <div className="space-y-2 p-3">
          {messages.length === 0 ? (
            <p className="py-8 text-center text-xs text-muted-foreground">
              Ask about suspicious files, next processors, or ingestion readiness.
            </p>
          ) : null}
          {messages.map((message, index) => (
            <div key={index} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cn(
                "max-w-[85%] rounded-md px-3 py-2 text-xs",
                message.role === "user" ? "bg-amber-500 text-white" : "bg-muted text-foreground"
              )}>
                {message.content}
              </div>
            </div>
          ))}
          {chatMutation.isPending ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
        </div>
      </ScrollArea>
      <div className="flex items-center gap-2 border-t border-border p-2">
        <Input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) send()
          }}
          placeholder="Ask the advisor..."
        />
        <Button size="icon" disabled={!input.trim() || chatMutation.isPending} onClick={send}>
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  )
}

function IngestDialog({
  open,
  onOpenChange,
  triageCase,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  triageCase: TriageCase
}) {
  const [targetCaseId, setTargetCaseId] = useState("")
  const [search, setSearch] = useState("")
  const [includeArtifacts, setIncludeArtifacts] = useState(true)
  const [userOnly, setUserOnly] = useState(true)
  const casesQuery = useQuery({
    queryKey: ["cases"],
    queryFn: () => casesAPI.list(),
    enabled: open,
  })
  const previewMutation = useMutation({
    mutationFn: () =>
      triageAPI.ingestPreview(triageCase.id, {
        target_case_id: targetCaseId,
        include_artifacts: includeArtifacts,
        file_filter: userOnly ? { is_user_file: true } : null,
      }),
    onError: (error) => toast.error(error.message),
  })
  const ingestMutation = useMutation({
    mutationFn: () =>
      triageAPI.ingest(triageCase.id, {
        target_case_id: targetCaseId,
        include_artifacts: includeArtifacts,
        file_filter: userOnly ? { is_user_file: true } : null,
      }),
    onSuccess: (result) => {
      toast.success(`Ingestion started: ${result.task_id}`)
      onOpenChange(false)
    },
    onError: (error) => toast.error(error.message),
  })
  const filteredCases = (casesQuery.data ?? []).filter((item) => {
    const needle = search.toLowerCase()
    return item.title.toLowerCase().includes(needle) || item.description?.toLowerCase().includes(needle)
  })
  const selectedCase = casesQuery.data?.find((item) => item.id === targetCaseId)
  const preview = previewMutation.data

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ingest Triage Files</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Target Investigation Case</label>
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search cases..." />
            <div className="mt-2 max-h-40 overflow-auto rounded-md border border-border">
              {casesQuery.isLoading ? <div className="p-4"><LoadingSpinner /></div> : null}
              {filteredCases.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => {
                    setTargetCaseId(item.id)
                    previewMutation.reset()
                  }}
                  className={cn(
                    "block w-full border-b border-border px-3 py-2 text-left text-sm last:border-b-0 hover:bg-muted/60",
                    targetCaseId === item.id && "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
                  )}
                >
                  <span className="block truncate font-medium">{item.title}</span>
                  {item.description ? <span className="block truncate text-xs text-muted-foreground">{item.description}</span> : null}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox checked={userOnly} onCheckedChange={(checked) => { setUserOnly(checked === true); previewMutation.reset() }} />
              User files only
            </label>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox checked={includeArtifacts} onCheckedChange={(checked) => { setIncludeArtifacts(checked === true); previewMutation.reset() }} />
              Include artifacts
            </label>
          </div>
          {preview ? (
            <div className="rounded-md border border-border bg-muted/30 p-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Target</span>
                <span className="font-medium">{selectedCase?.title ?? targetCaseId}</span>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                <StatTile label="Files" value={(preview.file_count ?? 0).toLocaleString()} />
                <StatTile label="Size" value={formatBytes(preview.total_size)} />
                <StatTile label="Artifacts" value={(preview.artifact_count ?? 0).toLocaleString()} />
              </div>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="outline" disabled={!targetCaseId || previewMutation.isPending} onClick={() => previewMutation.mutate()}>
            {previewMutation.isPending ? <LoadingSpinner size="sm" /> : <FileText className="size-4" />}
            Preview
          </Button>
          <Button disabled={!preview || !preview.file_count || ingestMutation.isPending} onClick={() => ingestMutation.mutate()}>
            {ingestMutation.isPending ? <LoadingSpinner size="sm" /> : <Upload className="size-4" />}
            Ingest
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function TriagePage() {
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)

  return (
    <div className="h-full overflow-hidden">
      <div className="grid h-full grid-cols-1 md:grid-cols-[360px_minmax(0,1fr)]">
        <TriageCaseList selectedId={selectedCaseId} onSelect={setSelectedCaseId} />
        {selectedCaseId ? (
          <TriageWorkbench caseId={selectedCaseId} onBack={() => setSelectedCaseId(null)} />
        ) : (
          <div className="flex h-full items-center justify-center bg-muted/20">
            <EmptyState
              icon={MessageSquare}
              title="Select a triage case"
              description="Create or open a triage case to scan, classify, profile, process and ingest evidence."
            />
          </div>
        )}
      </div>
    </div>
  )
}
