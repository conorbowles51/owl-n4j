// When a watched upload counts as stalled. Kept apart from the journey so a test can run it without a browser.
import { spawnSync } from "node:child_process"

const RELEASE_LOCK = "/mnt/owl-data/fin-wt/deploy-now.lock"

/** deploy-now holds this flock for a whole release; a queued one waits on it, so "held" spans a run of releases. */
export function releaseRunning(lock = RELEASE_LOCK) {
  return spawnSync("flock", ["-n", lock, "true"]).status === 1
}

export function stalled(stage, movedAt, minutes, now = Date.now()) {
  return stage === "sending" && now - movedAt > minutes * 60_000
}
