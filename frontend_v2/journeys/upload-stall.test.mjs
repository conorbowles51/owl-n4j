import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { setTimeout as wait } from "node:timers/promises"
import { test } from "node:test"
import { releaseRunning, stalled } from "./upload-stall.mjs"

test("a page quiet past the limit is stalled in every stage, not only sending", () => {
  const now = 100 * 60_000
  assert.equal(stalled("sending", now - 91 * 60_000, 90, now), true)
  assert.equal(stalled("sending", now - 89 * 60_000, 90, now), false)
  // P03, 6-8 Nov: the server refused the upload group, the page stayed in the hashing phase saying nothing, and the
  // old sending-only rule let three tries sit for 24 h each
  assert.equal(stalled("hashing", now - 91 * 60_000, 90, now), true)
  assert.equal(stalled("hashing", now - 89 * 60_000, 90, now), false)
  // before any stage is seen the page is still being handed the selection, which has no moving line to watch
  assert.equal(stalled(undefined, now - 91 * 60_000, 90, now), false)
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
