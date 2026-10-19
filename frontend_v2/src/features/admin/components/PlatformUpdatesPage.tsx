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
  DialogDescription,
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
      queryClient.setQueryData(
        ["admin", "platform-update", "status"],
        nextStatus
      )
      toast.success("Manual updater checked")
    },
    onError: () => {
      toast.error(
        "The manual update check could not be completed. Try again or view the technical details."
      )
    },
  })

  const deployMutation = useMutation({
    mutationFn: () => platformUpdateAPI.deploy(),
    onSuccess: (nextStatus) => {
      queryClient.setQueryData(
        ["admin", "platform-update", "status"],
        nextStatus
      )
      setConfirmOpen(false)
      toast.success("Manual update requested")
    },
    onError: () => {
      toast.error(
        "The manual update request could not be confirmed. Refresh information before trying again."
      )
    },
  })

  const isBusy =
    statusQuery.isFetching ||
    checkMutation.isPending ||
    deployMutation.isPending
  const deployDisabled =
    !presentation.canDeploy ||
    isBusy ||
    statusQuery.isError ||
    checkMutation.isError ||
    deployMutation.isError
  const refresh = async () => {
    const result = await statusQuery.refetch()
    if (!result.isError) {
      checkMutation.reset()
      deployMutation.reset()
      if (
        result.data?.deployment_running ||
        result.data?.deployment_status === "running"
      )
        setConfirmOpen(false)
    }
  }
  const errors = [
    ["Information request", statusQuery.error],
    ["Manual check request", checkMutation.error],
    ["Manual update request", deployMutation.error],
  ] as const

  return (
    <div className="space-y-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <CloudDownload className="size-4 text-amber-500" />
            <h1 className="font-display text-lg font-semibold">
              Loupe updates
            </h1>
          </div>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
            Understand how improvements reach Loupe and whether an administrator
            needs to act.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refresh()}
            disabled={isBusy}
          >
            <RefreshCw
              className={isBusy ? "size-3.5 animate-spin" : "size-3.5"}
            />
            Refresh information
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Automatic releases</CardTitle>
          <CardDescription>
            Published improvements are deployed automatically. You do not need
            to start the manual updater for those releases.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            This page does not report the progress or outcome of automatic
            releases.
          </p>
          <p className="text-muted-foreground">
            If you are waiting for a specific fix, ask your administrator
            whether its release has completed. A problem with the manual updater
            below does not mean that an automatic release failed.
          </p>
        </CardContent>
      </Card>

      {statusQuery.isError && (
        <div role="alert" className="rounded border p-3 text-sm">
          Update information could not be loaded. This does not confirm a
          deployment failure. Use Refresh information to try again.
        </div>
      )}
      {checkMutation.isError && (
        <div role="alert" className="rounded border p-3 text-sm">
          The manual update check could not be completed. Try Check for updates
          again, or ask an administrator to inspect the technical details.
        </div>
      )}
      {deployMutation.isError && !confirmOpen && (
        <div role="alert" className="rounded border p-3 text-sm">
          The manual update request could not be confirmed. Refresh information
          before trying again; the request may have reached the server.
        </div>
      )}

      <Card className="overflow-hidden border-primary/15 bg-gradient-to-br from-card via-card to-primary/5">
        <CardHeader className="border-b border-border/70">
          <CardTitle className="flex flex-wrap items-center gap-2">
            {presentation.badgeVariant === "success" ? (
              <CheckCircle2 className="size-4 text-emerald-500" />
            ) : presentation.badgeVariant === "danger" ||
              presentation.badgeVariant === "warning" ? (
              <AlertTriangle className="size-4 text-yellow-500" />
            ) : (
              <ServerCog className="size-4 text-amber-500" />
            )}
            Manual update (administrators)
            <Badge
              variant={
                statusQuery.isError ? "slate" : presentation.badgeVariant
              }
            >
              {statusQuery.isError
                ? "Information unavailable"
                : presentation.label}
            </Badge>
          </CardTitle>
          <CardDescription>
            {statusQuery.isError
              ? "The separate manual update option cannot be checked right now."
              : presentation.description}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 p-4 text-sm">
          <p>
            Last manual version check:{" "}
            {formatUpdateTimestamp(status?.last_checked_at)}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => checkMutation.mutate()}
              disabled={isBusy}
            >
              Check for updates
            </Button>
            <Button
              size="sm"
              disabled={deployDisabled}
              onClick={() => setConfirmOpen(true)}
              title={presentation.deployDisabledReason}
            >
              <Rocket className="size-3.5" /> Start manual update
            </Button>
          </div>
          {deployDisabled && (
            <p className="text-xs text-muted-foreground">
              {deployMutation.isError
                ? "Refresh information to check the previous request before starting another."
                : statusQuery.isError
                  ? "Refresh information before starting a manual update."
                  : checkMutation.isError
                    ? "Complete a successful check before starting a manual update."
                    : isBusy
                      ? "Wait for the current request to finish."
                      : presentation.deployDisabledReason}
            </p>
          )}
        </CardContent>
      </Card>

      <details className="rounded-lg border bg-card p-4 space-y-4">
        <summary className="cursor-pointer font-medium text-sm">
          Technical details for administrators
        </summary>
        <p className="text-xs text-muted-foreground">
          These details describe the manual updater and its repository
          comparison. A checkout revision is not proof that every running
          service or browser is using that release.
        </p>
        <div className="grid gap-4 md:grid-cols-4">
          <StatusTile
            label="Branch"
            value={status?.branch || "Unknown"}
            icon={<GitBranch className="size-3.5" />}
          />
          <StatusTile
            label="Local checkout revision"
            value={status?.local_short_sha || "Unknown"}
            mono
          />
          <StatusTile
            label="Checked available revision"
            value={status?.remote_short_sha || "Unknown"}
            mono
          />
          <StatusTile
            label="Last checked"
            value={formatUpdateTimestamp(status?.last_checked_at)}
          />
        </div>

        {errors
          .filter(([, error]) => error)
          .map(([label, error]) => (
            <div key={label} className="rounded border p-3 text-xs">
              <p className="font-medium">{label}</p>
              <pre className="whitespace-pre-wrap break-words mt-1">
                {error instanceof Error
                  ? error.message
                  : "No further detail is available."}
              </pre>
            </div>
          ))}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle className="text-sm">Manual updater setup</CardTitle>
              <CardDescription>
                The browser can only start the fixed self-update service.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <FieldRow
                label="Enabled"
                value={status ? (status.enabled ? "Yes" : "No") : "Unknown"}
              />
              <FieldRow
                label="Configured"
                value={status ? (status.configured ? "Yes" : "No") : "Unknown"}
              />
              <FieldRow
                label="Service"
                value={status?.service_name || "Unknown"}
                mono
              />
              <FieldRow
                label="Remote"
                value={status?.remote || "Unknown"}
                mono
              />
              <FieldRow
                label="Repository"
                value={status?.repo_dir || "Unknown"}
                mono
              />
              <FieldRow
                label="Manual updater state"
                value={status?.deployment_status || "Unknown"}
              />
              {status?.config_error && (
                <div className="rounded-md border border-yellow-500/25 bg-yellow-500/10 p-3 break-words text-yellow-800 dark:text-yellow-200">
                  {status.config_error}
                </div>
              )}
              {status?.last_check_error && (
                <pre className="rounded border p-3 whitespace-pre-wrap break-words">
                  {status.last_check_error}
                </pre>
              )}
              {status?.deployment_error && (
                <pre className="rounded border p-3 whitespace-pre-wrap break-words">
                  {status.deployment_error}
                </pre>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-80 min-w-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <TerminalSquare className="size-4 text-slate-500" />
                Captured deployment log
              </CardTitle>
              <CardDescription>
                Saved server output may describe an earlier update. It is not a
                live report of automatic deployment.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {status?.deploy_log_tail ? (
                <ScrollArea className="h-72 rounded-md border border-slate-200 bg-slate-950 text-slate-100 dark:border-slate-800">
                  <pre className="whitespace-pre-wrap break-all p-3 font-mono text-[11px] leading-relaxed">
                    {status.deploy_log_tail}
                  </pre>
                </ScrollArea>
              ) : (
                <div className="flex h-72 items-center justify-center rounded-md border border-dashed border-border text-xs text-muted-foreground">
                  No captured deployment log is available
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </details>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-sm">
              Start a manual update?
            </DialogTitle>
            <DialogDescription>
              Use this only when an administrator intends to update Loupe
              through the manual updater.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-muted-foreground">
              This requests a separate manual update. Loupe may briefly
              disconnect while it restarts. Save unfinished work before
              starting.
            </p>
            <details className="rounded-md border border-border bg-muted/40 p-3 text-xs space-y-2">
              <summary className="cursor-pointer">
                Technical version details
              </summary>
              <FieldRow
                label="From"
                value={status?.local_short_sha || "Unknown"}
                mono
              />
              <FieldRow
                label="To"
                value={status?.remote_short_sha || "Unknown"}
                mono
              />
              <FieldRow
                label="Branch"
                value={status?.branch || "Unknown"}
                mono
              />
            </details>
            {deployMutation.isError && (
              <div role="alert" className="rounded border p-3">
                The manual update request could not be confirmed. Refresh
                information before trying again; the request may have reached
                the server.
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2 flex"
                  disabled={isBusy}
                  onClick={() => void refresh()}
                >
                  Refresh information
                </Button>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={deployMutation.isPending}
              onClick={() => setConfirmOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={() => deployMutation.mutate()}
              disabled={deployDisabled}
            >
              <Rocket className="size-3.5" />
              {deployMutation.isPending
                ? "Requesting update…"
                : "Confirm manual update"}
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
      <div
        className={
          mono ? "mt-1 font-mono text-sm" : "mt-1 text-sm font-semibold"
        }
      >
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
