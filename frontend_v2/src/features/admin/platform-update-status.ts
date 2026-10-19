import type { PlatformUpdateStatus } from "./api"

export type PlatformUpdateTone =
  | "success"
  | "warning"
  | "danger"
  | "amber"
  | "slate"

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
      label: "Checking manual updater",
      description:
        "Loading information about the separate manual update option.",
      badgeVariant: "slate",
      canDeploy: false,
      deployDisabledReason: "Status has not loaded yet.",
    }
  }

  if (status.deployment_running || status.deployment_status === "running") {
    return {
      label: "Manual update running",
      description:
        "An administrator has started a manual update. Loupe may briefly reconnect while it finishes.",
      badgeVariant: "amber",
      canDeploy: false,
      deployDisabledReason: "A manual update is already running.",
    }
  }

  if (!status.enabled) {
    return {
      label: "Manual updates off",
      description:
        "Updating from this page is turned off. Automatic releases use a separate deployment process.",
      badgeVariant: "slate",
      canDeploy: false,
      deployDisabledReason: "The manual update option is turned off.",
    }
  }

  if (!status.configured) {
    return {
      label: "Manual update unavailable",
      description:
        "The manual update option needs administrator setup. This does not mean an automatic release has failed.",
      badgeVariant: "warning",
      canDeploy: false,
      deployDisabledReason:
        "An administrator needs to set up the manual updater first.",
    }
  }

  if (status.last_check_error) {
    return {
      label: "Manual check unavailable",
      description:
        "The manual updater could not compare versions. Check again, or ask an administrator to inspect the technical details.",
      badgeVariant: "warning",
      canDeploy: false,
      deployDisabledReason:
        "A successful version check is needed before starting a manual update.",
    }
  }

  if (status.deployment_status === "failed" || status.deployment_error) {
    return {
      label: "Manual update needs attention",
      description:
        "A manual update attempt reported a problem. An administrator should check its result before trying again. This is not the status of automatic releases.",
      badgeVariant: "warning",
      canDeploy: status.update_available && status.can_deploy,
      deployDisabledReason:
        status.update_available && status.can_deploy
          ? undefined
          : "Check the manual updater before starting another update.",
    }
  }

  if (status.update_available) {
    return {
      label: "Manual update available",
      description:
        "The manual updater found an available update. An administrator can choose whether to start it; automatic releases do not require this button.",
      badgeVariant: "amber",
      canDeploy: status.can_deploy,
      deployDisabledReason: status.can_deploy
        ? undefined
        : "The manual updater is not ready to start this update.",
    }
  }

  const local = status.local_sha || status.local_short_sha
  const remote = status.remote_sha || status.remote_short_sha
  if (!status.last_checked_at || !local || !remote || local !== remote) {
    return {
      label: "Version comparison unavailable",
      description:
        "There is no confirmed version comparison from the manual updater yet. Use Check for updates to request one.",
      badgeVariant: "slate",
      canDeploy: false,
      deployDisabledReason:
        "Check for updates before starting a manual update.",
    }
  }

  return {
    label: "No manual update available",
    description:
      "The last manual check found matching versions. This comparison does not confirm the progress or outcome of an automatic release.",
    badgeVariant: "success",
    canDeploy: false,
    deployDisabledReason: "The last manual check found no update to install.",
  }
}

export function formatUpdateTimestamp(value?: string | null): string {
  if (!value) return "Not yet checked"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "Time unavailable"
  return date.toLocaleString()
}
