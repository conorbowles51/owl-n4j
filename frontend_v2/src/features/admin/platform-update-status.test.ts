import { describe, expect, it } from "vitest"

import type { PlatformUpdateStatus } from "./api"
import { getPlatformUpdatePresentation } from "./platform-update-status"

const baseStatus: PlatformUpdateStatus = {
  enabled: true,
  configured: true,
  can_deploy: false,
  repo_dir: "/opt/owl-n4j",
  remote: "origin",
  branch: "main",
  service_name: "owl-self-update.service",
  update_available: false,
  deployment_running: false,
  deployment_status: "idle",
}

describe("getPlatformUpdatePresentation", () => {
  it("disables deployment when platform updates are disabled", () => {
    const presentation = getPlatformUpdatePresentation({
      ...baseStatus,
      enabled: false,
    })

    expect(presentation.label).toBe("Manual updates off")
    expect(presentation.description).toContain("Automatic releases")
    expect(presentation.canDeploy).toBe(false)
  })

  it("shows a not configured state when the systemd service is missing", () => {
    const presentation = getPlatformUpdatePresentation({
      ...baseStatus,
      configured: false,
      config_error: "Service owl-self-update.service is not loaded",
    })

    expect(presentation.label).toBe("Manual update unavailable")
    expect(presentation.description).not.toContain("owl-self-update.service")
    expect(presentation.description).toContain(
      "does not mean an automatic release has failed"
    )
  })

  it("enables deployment only when an update is available and the backend allows it", () => {
    const presentation = getPlatformUpdatePresentation({
      ...baseStatus,
      update_available: true,
      can_deploy: true,
    })

    expect(presentation.label).toBe("Manual update available")
    expect(presentation.canDeploy).toBe(true)
  })

  it("blocks deployment while an update is already running", () => {
    const presentation = getPlatformUpdatePresentation({
      ...baseStatus,
      update_available: true,
      can_deploy: true,
      deployment_running: true,
      deployment_status: "running",
    })

    expect(presentation.label).toBe("Manual update running")
    expect(presentation.canDeploy).toBe(false)
  })

  it("does not claim Loupe is up to date without a completed version comparison", () => {
    expect(getPlatformUpdatePresentation(baseStatus).label).toBe(
      "Version comparison unavailable"
    )
    expect(
      getPlatformUpdatePresentation({
        ...baseStatus,
        last_checked_at: "2026-09-25T12:00:00Z",
        local_sha: "a",
        remote_sha: "b",
      }).label
    ).toBe("Version comparison unavailable")
    const matched = getPlatformUpdatePresentation({
      ...baseStatus,
      last_checked_at: "2026-09-25T12:00:00Z",
      local_sha: "a",
      remote_sha: "a",
    })
    expect(matched.label).toBe("No manual update available")
    expect(matched.description).toContain("does not confirm")
  })

  it("describes a failed manual attempt without declaring automatic deployment failed", () => {
    const result = getPlatformUpdatePresentation({
      ...baseStatus,
      deployment_status: "failed",
      deployment_error: "sudo: not allowed",
      update_available: true,
      can_deploy: true,
    })
    expect(result.label).toBe("Manual update needs attention")
    expect(result.description).not.toContain("sudo")
    expect(result.canDeploy).toBe(true)
  })

  it("keeps raw check errors out of the primary description", () => {
    const result = getPlatformUpdatePresentation({
      ...baseStatus,
      last_check_error: "fatal: unknown git remote",
    })
    expect(result.label).toBe("Manual check unavailable")
    expect(result.description).not.toContain("fatal")
    expect(result.canDeploy).toBe(false)
  })
})
