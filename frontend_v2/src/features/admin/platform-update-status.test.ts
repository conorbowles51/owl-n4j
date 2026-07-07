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

    expect(presentation.label).toBe("Disabled")
    expect(presentation.canDeploy).toBe(false)
  })

  it("shows a not configured state when the systemd service is missing", () => {
    const presentation = getPlatformUpdatePresentation({
      ...baseStatus,
      configured: false,
      config_error: "Service owl-self-update.service is not loaded",
    })

    expect(presentation.label).toBe("Not configured")
    expect(presentation.description).toContain("not loaded")
  })

  it("enables deployment only when an update is available and the backend allows it", () => {
    const presentation = getPlatformUpdatePresentation({
      ...baseStatus,
      update_available: true,
      can_deploy: true,
    })

    expect(presentation.label).toBe("Update available")
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

    expect(presentation.label).toBe("Updating")
    expect(presentation.canDeploy).toBe(false)
  })
})
