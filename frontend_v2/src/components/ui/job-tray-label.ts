import type { TrayJob } from "./job-tray"

export function trayLabel(jobs: TrayJob[]): string {
  const running = jobs.filter((j) => j.state === "running").length
  const done = jobs.filter((j) => j.state === "done").length
  const failed = jobs.filter((j) => j.state === "failed").length
  const parts = [] as string[]
  if (running) parts.push(`${running} running`)
  if (done) parts.push(`${done} done`)
  if (failed) parts.push(`${failed} stopped`)
  return parts.length ? `Jobs (${parts.join(", ")})` : "Jobs (none)"
}
