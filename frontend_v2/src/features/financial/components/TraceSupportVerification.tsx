import { useEffect, useRef, useState } from "react"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"

const digest = z.string().regex(/^[a-f0-9]{64}$/)
const verification = z.object({
  schema_version: z.literal("loupe.financial.trace_support_verification/1"),
  archive_sha256: digest,
  case_id: z.string(),
  member_count: z.number().int().nonnegative().max(64),
  status: z.enum([
    "verified_bytes_matching_rebuild",
    "verified_bytes_matching_calculations",
    "verified_bytes_different_rebuild",
  ]),
  changed_members: z.array(z.string()).max(64),
  manifest_metadata_changed: z.boolean(),
  replay_version_changes: z
    .array(
      z.object({
        member: z.string(),
        captured_replay_code_version: z.string().nullable(),
        current_replay_code_version: z.string().nullable(),
      })
    )
    .max(8),
  checkpoint_status: z.enum(["not_supplied", "matches_supplied_digest"]),
  limitation: z.string(),
})
type Verification = z.infer<typeof verification>

export function TraceSupportVerification({ caseId }: { caseId: string }) {
  const [file, setFile] = useState<File | null>(null)
  const [pin, setPin] = useState("")
  const [result, setResult] = useState<Verification | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const request = useRef<AbortController | null>(null)
  useEffect(
    () => () => {
      request.current?.abort()
      request.current = null
    },
    []
  )
  const clear = () => {
    setResult(null)
    setError("")
  }
  const check = async () => {
    if (!file || request.current) return
    clear()
    if (file.size > 256 * 1024 * 1024) {
      setError("Choose a package no larger than 256 MiB.")
      return
    }
    if (pin && !digest.safeParse(pin).success) {
      setError(
        "The saved SHA-256 must contain 64 lowercase hexadecimal characters."
      )
      return
    }
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    const timeout = setTimeout(() => controller.abort(), 120000)
    try {
      const bytes = await file.arrayBuffer()
      const selectedDigest = Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
        (b) => b.toString(16).padStart(2, "0")
      ).join("")
      if (controller.signal.aborted) return
      if (pin && pin !== selectedDigest)
        throw Error("This file differs from the previously saved digest.")
      const body = new FormData()
      body.set("archive", file)
      const token = localStorage.getItem("authToken")
      const response = await fetch(
        candidateUrl("trace-support-verification", caseId) +
          (pin ? `&expected_sha256=${pin}` : ""),
        {
          method: "POST",
          body,
          credentials: "include",
          signal: controller.signal,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      )
      if (!response.ok)
        throw Error(
          "The package could not be verified. Check that it is a tracing audit ZIP for this case."
        )
      const text = await response.text()
      if (text.length > 1024 * 1024)
        throw Error("Verification response exceeds its limit.")
      const parsed = verification.parse(JSON.parse(text))
      if (
        parsed.case_id !== caseId ||
        parsed.archive_sha256 !== selectedDigest ||
        parsed.checkpoint_status !==
          (pin ? "matches_supplied_digest" : "not_supplied")
      )
        throw Error("Verification returned for a different file or case.")
      if (
        parsed.status !== "verified_bytes_different_rebuild" &&
        (parsed.changed_members.length || parsed.manifest_metadata_changed)
      )
        throw Error("Verification summary is inconsistent.")
      if (!controller.signal.aborted) setResult(parsed)
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Verification failed.")
      else if (request.current === controller)
        setError("Verification was interrupted. You can try again.")
    } finally {
      clearTimeout(timeout)
      if (request.current === controller) {
        request.current = null
        setBusy(false)
      }
    }
  }
  const save = () => {
    if (!result) return
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" })
    )
    const link = document.createElement("a")
    link.href = url
    link.download = "loupe-support-verification.json"
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <details className="rounded border p-3">
      <summary className="cursor-pointer text-sm font-medium">
        Check a saved tracing audit package
      </summary>
      <div className="mt-3 space-y-3 text-sm">
        <p>
          Check the saved files and rerun their recorded calculations. This does
          not change the case.
        </p>
        <label className="block">
          Tracing audit ZIP
          <input
            className="mt-1 block w-full"
            type="file"
            accept=".zip,application/zip"
            disabled={busy}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              clear()
            }}
          />
        </label>
        <label className="block">
          Previously saved SHA-256 (optional)
          <input
            className="mt-1 block w-full rounded border p-2 font-mono"
            value={pin}
            disabled={busy}
            onChange={(e) => {
              setPin(e.target.value.trim())
              clear()
            }}
          />
        </label>
        <p className="text-muted-foreground">
          A digest retained separately can identify a replaced package. Leave it
          blank if none was saved.
        </p>
        <Button
          type="button"
          variant="outline"
          disabled={!file || busy}
          onClick={check}
        >
          {busy ? "Checking package…" : "Check package"}
        </Button>
        {error && <p role="alert">{error}</p>}
        {result && (
          <section
            aria-label="Saved package verification"
            className="space-y-2"
          >
            <p role="status" className="font-medium">
              {result.status === "verified_bytes_different_rebuild"
                ? "Files match their recorded hashes, but the rebuilt support differs. Review the differences."
                : "Files and recalculated results match."}
            </p>
            <p>{result.member_count} recorded files checked.</p>
            {result.replay_version_changes.length > 0 && (
              <p>
                The calculations match using a different code revision. Both
                revisions are retained in the verification download.
              </p>
            )}
            {result.manifest_metadata_changed && (
              <p>The package description differs from the current rebuild.</p>
            )}
            {result.changed_members.length > 0 && (
              <ul className="list-disc pl-5">
                {result.changed_members.map((name) => (
                  <li className="break-all" key={name}>
                    {name}
                  </li>
                ))}
              </ul>
            )}
            <details>
              <summary className="cursor-pointer">
                What this check establishes
              </summary>
              <p className="mt-2">{result.limitation}</p>
            </details>
            <Button type="button" variant="outline" onClick={save}>
              Download verification
            </Button>
          </section>
        )}
      </div>
    </details>
  )
}
