// When a watched upload counts as stalled. Kept apart from the journey so a test can run it without a browser.
import { spawnSync } from "node:child_process"

const RELEASE_LOCK = "/mnt/owl-data/fin-wt/deploy-now.lock"

/** deploy-now holds this flock for a whole release; a queued one waits on it, so "held" spans a run of releases. */
export function releaseRunning(lock = RELEASE_LOCK) {
  return spawnSync("flock", ["-n", lock, "true"]).status === 1
}

export function stalled(stage, movedAt, minutes, now = Date.now()) {
  // any stage once the page is working: every phase prints moving counts, so a line unchanged for the limit is a
  // dead page or a refusal the page did not voice (P03, 6-8 Nov: a refused upload left the page quiet in the
  // hashing phase for 24 h, three tries in a row, because this rule read "sending" only)
  return Boolean(stage) && now - movedAt > minutes * 60_000
}
