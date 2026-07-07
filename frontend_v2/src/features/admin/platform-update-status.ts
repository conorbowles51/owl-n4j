import type { PlatformUpdateStatus } from "./api"

export type PlatformUpdateTone = "success" | "warning" | "danger" | "amber" | "slate"

export interface PlatformUpdatePresentation {
  label: string
  description: string
  badgeVariant: PlatformUpdateTone
  canDeploy: boolean
  deployDisabledReason?: string
}

export function getPlatformUpdatePresentation(
  status?: PlatformUpdateStatus | null
): PlatformUpdatePresentation {
  if (!status) {
    return {
      label: "Checking",
      description: "Looking for the latest platform version.",
      badgeVariant: "slate",
      canDeploy: false,
      deployDisabledReason: "Status has not loaded yet.",
    }
  }

  if (!status.enabled) {
    return {
      label: "Disabled",
      description: "Admin-triggered updates are turned off on this server.",
      badgeVariant: "slate",
      canDeploy: false,
      deployDisabledReason: "Platform updates are disabled.",
    }
  }

  if (!status.configured) {
    return {
      label: "Not configured",
      description: status.config_error || "The self-update service is not ready on this server.",
      badgeVariant: "warning",
      canDeploy: false,
      deployDisabledReason: "The update service is not configured.",
    }
  }

  if (status.deployment_running || status.deployment_status === "running") {
    return {
      label: "Updating",
      description: "A platform update is currently running.",
      badgeVariant: "amber",
      canDeploy: false,
      deployDisabledReason: "An update is already running.",
    }
  }

  if (status.last_check_error) {
    return {
      label: "Check failed",
      description: status.last_check_error,
      badgeVariant: "danger",
      canDeploy: false,
      deployDisabledReason: "Resolve the update check error first.",
    }
  }

  if (status.update_available) {
    return {
      label: "Update available",
      description: "A newer version is available on the configured branch.",
      badgeVariant: "amber",
      canDeploy: status.can_deploy,
      deployDisabledReason: status.can_deploy ? undefined : "The server is not ready to deploy yet.",
    }
  }

  return {
    label: "Up to date",
    description: "This server is already running the latest checked commit.",
    badgeVariant: "success",
    canDeploy: false,
    deployDisabledReason: "No update is available.",
  }
}

export function formatUpdateTimestamp(value?: string | null): string {
  if (!value) return "Never"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}
