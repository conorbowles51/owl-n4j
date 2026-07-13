import { useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle2,
  CloudDownload,
  GitBranch,
  RefreshCw,
  Rocket,
  ServerCog,
  TerminalSquare,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { platformUpdateAPI } from "@/features/admin/api"
import {
  formatUpdateTimestamp,
  getPlatformUpdatePresentation,
} from "@/features/admin/platform-update-status"

export function PlatformUpdatesPage() {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const queryClient = useQueryClient()

  const statusQuery = useQuery({
    queryKey: ["admin", "platform-update", "status"],
    queryFn: () => platformUpdateAPI.getStatus(),
    refetchInterval: (query) =>
      query.state.data?.deployment_running ? 5000 : 60000,
  })

  const status = statusQuery.data
  const presentation = getPlatformUpdatePresentation(status)

  const checkMutation = useMutation({
    mutationFn: () => platformUpdateAPI.check(),
    onSuccess: (nextStatus) => {
      queryClient.setQueryData(["admin", "platform-update", "status"], nextStatus)
      toast.success("Update check complete")
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Update check failed")
    },
  })

  const deployMutation = useMutation({
    mutationFn: () => platformUpdateAPI.deploy(),
    onSuccess: (nextStatus) => {
      queryClient.setQueryData(["admin", "platform-update", "status"], nextStatus)
      setConfirmOpen(false)
      toast.success("Platform update started")
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to start update")
    },
  })

  const isBusy =
    statusQuery.isFetching || checkMutation.isPending || deployMutation.isPending
  const deployDisabled = !presentation.canDeploy || deployMutation.isPending

  return (
    <div className="space-y-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <CloudDownload className="size-4 text-amber-500" />
            <h1 className="text-lg font-semibold">Platform Updates</h1>
            <Badge variant={presentation.badgeVariant}>{presentation.label}</Badge>
          </div>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
            Check the deployed branch and start the server update service when a
            new version is ready.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => checkMutation.mutate()}
            disabled={isBusy}
          >
            <RefreshCw className={isBusy ? "size-3.5 animate-spin" : "size-3.5"} />
            Check now
          </Button>
          <Button
            size="sm"
            disabled={deployDisabled}
            onClick={() => setConfirmOpen(true)}
            title={presentation.deployDisabledReason}
          >
            <Rocket className="size-3.5" />
            Update platform
          </Button>
        </div>
      </div>

      <Card className="overflow-hidden border-slate-200/80 bg-[linear-gradient(135deg,#ffffff_0%,#f8fafc_100%)] dark:border-slate-800 dark:bg-[linear-gradient(135deg,#0b1120_0%,#111827_100%)]">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="flex items-center gap-2">
            {presentation.badgeVariant === "success" ? (
              <CheckCircle2 className="size-4 text-emerald-500" />
            ) : presentation.badgeVariant === "danger" ||
              presentation.badgeVariant === "warning" ? (
              <AlertTriangle className="size-4 text-amber-500" />
            ) : (
              <ServerCog className="size-4 text-amber-500" />
            )}
            Update status
          </CardTitle>
          <CardDescription>{presentation.description}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 p-4 md:grid-cols-4">
          <StatusTile
            label="Branch"
            value={status?.branch || "Unknown"}
            icon={<GitBranch className="size-3.5" />}
          />
          <StatusTile
            label="Deployed"
            value={status?.local_short_sha || "Unknown"}
            mono
          />
          <StatusTile
            label="Latest"
            value={status?.remote_short_sha || "Unknown"}
            mono
          />
          <StatusTile
            label="Last checked"
            value={formatUpdateTimestamp(status?.last_checked_at)}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Server setup</CardTitle>
            <CardDescription>
              The browser can only start the fixed self-update service.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <FieldRow label="Enabled" value={status?.enabled ? "Yes" : "No"} />
            <FieldRow label="Configured" value={status?.configured ? "Yes" : "No"} />
            <FieldRow label="Service" value={status?.service_name || "Unknown"} mono />
            <FieldRow label="Remote" value={status?.remote || "Unknown"} mono />
            <FieldRow label="Repository" value={status?.repo_dir || "Unknown"} mono />
            {status?.config_error && (
              <div className="rounded-md border border-amber-500/25 bg-amber-500/10 p-3 text-amber-700 dark:text-amber-300">
                {status.config_error}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="min-h-80">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <TerminalSquare className="size-4 text-slate-500" />
              Latest deploy log
            </CardTitle>
            <CardDescription>
              Showing the latest captured output from deploy/logs.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {status?.deploy_log_tail ? (
              <ScrollArea className="h-72 rounded-md border border-slate-200 bg-slate-950 text-slate-100 dark:border-slate-800">
                <pre className="whitespace-pre-wrap p-3 font-mono text-[11px] leading-relaxed">
                  {status.deploy_log_tail}
                </pre>
              </ScrollArea>
            ) : (
              <div className="flex h-72 items-center justify-center rounded-md border border-dashed border-border text-xs text-muted-foreground">
                No deploy log found yet
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-sm">Start platform update?</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-muted-foreground">
              This starts the server update service. Loupe may briefly disconnect
              while the backend and frontend restart.
            </p>
            <div className="rounded-md border border-border bg-muted/40 p-3 text-xs">
              <FieldRow label="From" value={status?.local_short_sha || "Unknown"} mono />
              <FieldRow label="To" value={status?.remote_short_sha || "Unknown"} mono />
              <FieldRow label="Branch" value={status?.branch || "Unknown"} mono />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => deployMutation.mutate()}
              disabled={deployMutation.isPending}
            >
              <Rocket className="size-3.5" />
              {deployMutation.isPending ? "Starting..." : "Start update"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function StatusTile({
  label,
  value,
  icon,
  mono = false,
}: {
  label: string
  value: string
  icon?: ReactNode
  mono?: boolean
}) {
  return (
    <div className="rounded-md border border-border bg-background/70 p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className={mono ? "mt-1 font-mono text-sm" : "mt-1 text-sm font-semibold"}>
        {value}
      </div>
    </div>
  )
}

function FieldRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span
        className={
          mono
            ? "min-w-0 break-all text-right font-mono text-[11px]"
            : "min-w-0 text-right font-medium"
        }
      >
        {value}
      </span>
    </div>
  )
}
