import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { setTimeout as wait } from "node:timers/promises"
import { test } from "node:test"
import { releaseRunning, stalled } from "./upload-stall.mjs"

test("only a sending page past the limit is stalled", () => {
  const now = 100 * 60_000
  assert.equal(stalled("sending", now - 91 * 60_000, 90, now), true)
  assert.equal(stalled("sending", now - 89 * 60_000, 90, now), false)
  assert.equal(stalled("hashing", now - 91 * 60_000, 90, now), false)
})

test("a held release lock reads as a release running, a free one does not", async () => {
  const lock = join(mkdtempSync(join(tmpdir(), "stall-")), "lock")
  writeFileSync(lock, "")
  assert.equal(releaseRunning(lock), false)
  const holder = spawn("flock", [lock, "sleep", "5"])
  await wait(500)
  assert.equal(releaseRunning(lock), true)
  holder.kill()
})
