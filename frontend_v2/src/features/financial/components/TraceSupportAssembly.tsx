import { sha256Hex as sha } from "@/lib/browser-crypto"
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"

import { PackageFilePicker } from "./PackageFilePicker"

type Marking = "unmarked" | "confidential" | "privileged_confidential"

export function TraceSupportAssembly({ caseId }: { caseId: string }) {
  const [scenarios, setScenarios] = useState<File[]>([])
  const [ledger, setLedger] = useState<File | null>(null)
  const [review, setReview] = useState<File | null>(null)
  const [predictions, setPredictions] = useState<File | null>(null)
  const [marking, setMarking] = useState<Marking>("unmarked")
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("")
  const request = useRef<AbortController | null>(null)
  useEffect(
    () => () => {
      request.current?.abort()
      request.current = null
    },
    []
  )
  const changed = () => {
    setError("")
    setMessage("")
  }
  const assemble = async () => {
    if (request.current) return
    changed()
    if ((!scenarios.length && !ledger) || scenarios.length > 8) {
      setError("Select a saved ledger export or up to eight tracing scenarios.")
      return
    }
    if (Boolean(review) !== Boolean(predictions)) {
      setError(
        "Attach both the reconciled review record and extraction predictions, or leave both empty."
      )
      return
    }
    if (
      [...scenarios, review, predictions].some(
        (file) => file && file.size > 16 * 1024 * 1024
      ) ||
      (ledger && ledger.size > 128 * 1024 * 1024) ||
      scenarios.reduce((n, f) => n + f.size, 0) > 64 * 1024 * 1024
    ) {
      setError(
        "Scenarios and validation files must each be within 16 MiB, all scenarios within 64 MiB, and the ledger ZIP within 128 MiB."
      )
      return
    }
    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    const timeout = setTimeout(() => controller.abort(), 120000)
    try {
      const hashFile = async (file: File | null) =>
        file ? sha(await file.arrayBuffer()) : null
      const inputs = {
        ledger: await hashFile(ledger),
        predictions: await hashFile(predictions),
        review: await hashFile(review),
        scenarios: await Promise.all(scenarios.map(hashFile)),
      }
      const inputDigest = await sha(
        new TextEncoder().encode(JSON.stringify(inputs)).buffer
      )
      if (controller.signal.aborted) return
      const body = new FormData()
      for (const file of scenarios) body.append("scenarios", file)
      if (ledger) body.set("ledger", ledger)
      if (review) body.set("review", review)
      if (predictions) body.set("predictions", predictions)
      const token = localStorage.getItem("authToken")
      const response = await fetch(
        candidateUrl("trace-support-assembly", caseId) +
          `&privilege_marking=${marking}`,
        {
          method: "POST",
          body,
          credentials: "include",
          signal: controller.signal,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      )
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw Error(
          typeof detail?.detail === "string" && detail.detail.length < 2000
            ? detail.detail
            : "The review package could not be prepared."
        )
      }
      if (
        response.headers.get("content-type")?.split(";")[0] !==
          "application/zip" ||
        response.headers.get("X-Loupe-Case-Id") !== caseId ||
        response.headers.get("X-Loupe-Privilege-Marking") !== marking ||
        response.headers.get("X-Loupe-Assembly-Inputs-Sha256") !== inputDigest
      )
        throw Error(
          "Package response does not match the selected case, files or marking."
        )
      const bytes = await response.arrayBuffer()
      if (bytes.byteLength > 256 * 1024 * 1024)
        throw Error("Package exceeds the download limit.")
      if ((await sha(bytes)) !== response.headers.get("X-Loupe-Archive-Sha256"))
        throw Error("Package integrity check failed.")
      if (controller.signal.aborted) return
      const url = URL.createObjectURL(
        new Blob([bytes], { type: "application/zip" })
      )
      const link = document.createElement("a")
      link.href = url
      link.download = "loupe-review-support.zip"
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage(
        "Review package prepared and checked. Open review-index.html inside the ZIP for the contents, results and missing support. Original captures retain their separate scopes and markings."
      )
    } catch (e) {
      if (request.current === controller)
        setError(
          controller.signal.aborted
            ? "Preparation was interrupted. Check your downloads before trying again."
            : e instanceof Error
              ? e.message
              : "Package preparation failed."
        )
    } finally {
      clearTimeout(timeout)
      if (request.current === controller) {
        request.current = null
        setBusy(false)
      }
    }
  }
  return (
    <details className="rounded border p-3">
      <summary className="cursor-pointer text-sm font-medium">
        Assemble a review package
      </summary>
      <div className="mt-3 space-y-3 text-sm">
        <p>
          Share a saved transaction export, tracing calculations, or both in one
          ZIP. Start with the ledger ZIP downloaded from Transactions. You can
          add saved tracing scenarios if you used them in your investigation.
          Original files and their recorded filters are kept in the package.
        </p>
        <PackageFilePicker
          label="Saved ledger export (ZIP)"
          button="Choose ledger ZIP"
          accept=".zip,application/zip"
          files={ledger ? [ledger] : []}
          disabled={busy}
          onChange={(files) => {
            setLedger(files[0] ?? null)
            changed()
          }}
        />
        <PackageFilePicker
          label="Saved tracing scenarios (JSON)"
          button="Choose scenarios"
          accept=".json,application/json"
          files={scenarios}
          multiple
          disabled={busy}
          onChange={(files) => {
            setScenarios(files)
            changed()
          }}
        />
        <p>
          {scenarios.length} of 8 scenarios selected. Optional when you attach a
          ledger export. Save scenarios from the conditional tracing workbench.
        </p>
        <details>
          <summary className="cursor-pointer">
            Attach reviewed extraction validation (optional)
          </summary>
          <div className="mt-2 space-y-2">
            <p>
              Use a reconciled two-reader record and its extraction predictions.
              Calculations are checked again; synthetic labels remain identified
              as synthetic.
            </p>
            <PackageFilePicker
              label="Reconciled review record (JSON)"
              button="Choose review record"
              accept=".json,application/json"
              files={review ? [review] : []}
              disabled={busy}
              onChange={(files) => {
                setReview(files[0] ?? null)
                changed()
              }}
            />
            <PackageFilePicker
              label="Extraction predictions (JSON)"
              button="Choose extraction results"
              accept=".json,application/json"
              files={predictions ? [predictions] : []}
              disabled={busy}
              onChange={(files) => {
                setPredictions(files[0] ?? null)
                changed()
              }}
            />
          </div>
        </details>
        <label className="block">
          Review package marking
          <select
            aria-label="Review package marking"
            className="ml-2 rounded border p-1"
            value={marking}
            disabled={busy}
            onChange={(e) => {
              setMarking(e.target.value as Marking)
              changed()
            }}
          >
            <option value="unmarked">No privilege marking</option>
            <option value="confidential">Confidential</option>
            <option value="privileged_confidential">
              Privileged and confidential
            </option>
          </select>
        </label>
        <p>
          This marks the package description. Enclosed files retain their
          original markings. Assembly does not establish complete custody or an
          expert opinion.
        </p>
        <Button
          type="button"
          variant="outline"
          disabled={busy || (!scenarios.length && !ledger)}
          onClick={assemble}
        >
          {busy ? "Preparing package…" : "Prepare and download review package"}
        </Button>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
      </div>
    </details>
  )
}
