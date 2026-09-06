/**
 * Overruling a hold on a file, and the refusal that asks for it.
 *
 * Two kinds of test, the same two as `api.adjudication.test.ts`.
 *
 * The first kind checks what this file sends. This is the only call in the
 * financial feature that puts material into the document pipeline which no
 * reader could vouch for, and it carries a written justification recorded
 * verbatim against a named person. A request that lands on the wrong path,
 * names the wrong case, or drops the justification into a query string the
 * endpoint does not read, fails in a way nobody sees until someone asks who
 * admitted a file and the log cannot say.
 *
 * The second kind reads the backend source and requires the two languages to
 * still agree. Three files have to agree here rather than one, because the
 * exchange has two halves in two places: the gate raises the refusal, the
 * service answers the admission, and the router decides which outcomes are
 * answers and which are errors.
 *
 * The failure that matters most is `nothing_to_override` becoming an error.
 * It is a fact rather than a fault -- the router is not holding the file, so
 * there is no no to overrule and nothing stops it being processed. If the
 * backend ever turned it into a 4xx, this build would show a person a failure
 * for a file that was never blocked, and the honest answer would be gone.
 */

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  FILE_ADMISSION_FIELDS,
  FILE_ADMISSION_OUTCOMES,
  HELD_FILE_FIELDS,
  HELD_ROUTE_OUTCOMES,
  UNADMITTED_FILES_ERROR,
  UNADMITTED_FILES_REFUSAL_FIELDS,
  financialAPI,
  type FileAdmission,
} from "./api"

const here = dirname(fileURLToPath(import.meta.url))
const backend = (...parts: string[]) =>
  resolve(here, "../../../../backend", ...parts)

function read(path: string): string {
  return readFileSync(path, "utf8")
}

/**
 * The body of a Python block, from its header to the next line that starts in
 * column one.
 */
function pythonBlock(source: string, header: string): string {
  const opens = source.indexOf(header)
  expect(opens, `${header} is no longer declared`).toBeGreaterThan(-1)
  const next = source.slice(opens + header.length).search(/\n(?=\S)/)
  return next === -1
    ? source.slice(opens)
    : source.slice(opens, opens + header.length + next)
}

/**
 * The body of an *indented* Python block, ending at the first later line
 * indented no further than its header.
 *
 * `pythonBlock` above cannot do this job here. It ends a block at the next
 * line in column one, which is right for a top-level class and wrong for a
 * method inside one: `admission_gate.py` declares `as_dict` twice, on two
 * classes, and a search from the top of the file finds whichever comes first
 * whatever was asked for. Scoping to the class and then to the method inside
 * it is what keeps this test asserting about the shape it names.
 */
function indentedBlock(source: string, header: string): string {
  const at = source.indexOf(header)
  expect(at, `${header} is no longer declared`).toBeGreaterThan(-1)
  const indent = header.length - header.trimStart().length
  const kept: string[] = []
  for (const line of source.slice(at + header.length).split("\n")) {
    if (line.trim() === "") {
      kept.push(line)
      continue
    }
    if (line.length - line.trimStart().length <= indent) break
    kept.push(line)
  }
  return header + kept.join("\n")
}

/** The keys a class's `as_dict` returns, scoped to that class. */
function asDictKeys(source: string, classHeader: string): string[] {
  const body = indentedBlock(
    indentedBlock(source, classHeader),
    "    def as_dict(self) -> dict[str, Any]:"
  )
  return [...body.matchAll(/^ {12}"(\w+)":/gm)].map((m) => m[1])
}

function enumMembers(source: string, header: string): string[] {
  const block = pythonBlock(source, header)
  return [...block.matchAll(/^ {4}(\w+) = "([^"]*)"/gm)].map((m) => m[2])
}

/* ------------------------------------------------------------------ *
 * What this file sends
 * ------------------------------------------------------------------ */

/**
 * A stub that builds a fresh response per call. See `api.adjudication.test.ts`
 * for why this is not `mockResolvedValue` of a single `Response`.
 */
function answers(body: unknown): void {
  vi.mocked(globalThis.fetch).mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
  )
}

const ADMITTED: FileAdmission = {
  file_id: "file-1",
  outcome: "admitted",
  admitted: true,
  routed_to: "document_pipeline",
  reason: "Statement confirmed against the production index.",
  file_name: "march.pdf",
  route_outcome: "ambiguous",
  detected_format: "ofx",
  claimants: ["ofx", "qfx"],
  adjudication_id: "adj-1",
}

function requestedUrl(): string {
  return String(vi.mocked(globalThis.fetch).mock.calls[0][0])
}

function requestedInit(): RequestInit {
  return vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit
}

function sentBody(): unknown {
  return JSON.parse(String(requestedInit().body))
}

describe("the admission call", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    answers(ADMITTED)
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("posts to the admit route for the named file", async () => {
    await financialAPI.admitFile({
      caseId: "case-1",
      fileId: "file-1",
      reason: "Confirmed against the production index.",
    })

    expect(new URL(requestedUrl(), "http://loupe.test").pathname).toBe(
      "/api/financial/files/file-1/admit"
    )
    expect(requestedInit().method).toBe("POST")
  })

  it("names the case in the query string, under the name the endpoint reads", async () => {
    // The case is how the backend decides whether this caller may record a
    // decision against this file at all. Sent under any other name it is
    // absent and the request is rejected rather than misapplied.
    await financialAPI.admitFile({
      caseId: "case-1",
      fileId: "file-1",
      reason: "Confirmed.",
    })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(Object.fromEntries(url.searchParams)).toEqual({ case_id: "case-1" })
  })

  it("puts the justification in the body, wrapped under its own key", async () => {
    // The backend declares `reason` with `embed=True`, so it reads
    // `{"reason": "..."}` and not a bare string. Sent bare, FastAPI rejects
    // the request; sent in the query string it is silently absent.
    await financialAPI.admitFile({
      caseId: "case-1",
      fileId: "file-1",
      reason: "Confirmed against the production index.",
    })

    expect(sentBody()).toEqual({
      reason: "Confirmed against the production index.",
    })
    expect(
      new URL(requestedUrl(), "http://loupe.test").searchParams.has("reason")
    ).toBe(false)
  })

  it("carries a justification through unaltered, whatever is in it", async () => {
    const reason =
      'Produced as "MARCH STMT.OFX"; two readers claim it.\nSee the index, p.2.'
    await financialAPI.admitFile({
      caseId: "case-1",
      fileId: "file-1",
      reason,
    })

    expect(sentBody()).toEqual({ reason })
  })

  it("sends nothing about what the router found", async () => {
    // The backend re-reads the finding from the file rather than taking it
    // from the request, so a caller cannot put a chosen finding into the
    // permanent record. If this call ever started sending one, the record
    // would begin describing what the interface believed instead of what was
    // there.
    await financialAPI.admitFile({
      caseId: "case-1",
      fileId: "file-1",
      reason: "Confirmed.",
    })

    expect(Object.keys(sentBody() as object)).toEqual(["reason"])
  })

  it("escapes the file identifier into the path", async () => {
    await financialAPI.admitFile({
      caseId: "case one",
      fileId: "file/1 2",
      reason: "Confirmed.",
    })

    const url = new URL(requestedUrl(), "http://loupe.test")
    expect(url.pathname).toBe("/api/financial/files/file%2F1%202/admit")
    expect(url.searchParams.get("case_id")).toBe("case one")
  })

  it("returns the answer rather than reducing it to whether it worked", async () => {
    // `nothing_to_override` and `refused` both come back 200. Collapsing the
    // response to a boolean would report the first as a failure, when it
    // means the file was never held and can be processed as it stands.
    answers({
      ...ADMITTED,
      outcome: "nothing_to_override",
      admitted: false,
      routed_to: "held",
      reason: "The router is not holding this file.",
      adjudication_id: null,
    })

    const result = await financialAPI.admitFile({
      caseId: "case-1",
      fileId: "file-1",
      reason: "Confirmed.",
    })

    expect(result.outcome).toBe("nothing_to_override")
    expect(result.admitted).toBe(false)
    expect(result.reason).toBe("The router is not holding this file.")
  })

  it("keeps the claimants it was given rather than flattening them", async () => {
    // More than one reader claiming a file is the whole of what `ambiguous`
    // means. A screen that drops the list can say a file was ambiguous but
    // not what it was ambiguous between.
    const result = await financialAPI.admitFile({
      caseId: "case-1",
      fileId: "file-1",
      reason: "Confirmed.",
    })

    expect(result.claimants).toEqual(["ofx", "qfx"])
  })
})

/* ------------------------------------------------------------------ *
 * What the backend still says
 * ------------------------------------------------------------------ */

describe("the admission contract", () => {
  const routerSource = read(backend("routers", "financial_adjudication.py"))
  const serviceSource = read(backend("services", "financial", "admit_file.py"))
  const gateSource = read(backend("services", "financial", "admission_gate.py"))

  it("still mounts the admit route where this file posts it", () => {
    expect(routerSource).toContain('prefix="/api/financial"')
    expect(routerSource).toContain('@router.post("/files/{file_id}/admit")')
  })

  it("still reads case_id and an embedded reason on the admit route", () => {
    const block = pythonBlock(
      routerSource,
      "async def admit_file_to_document_pipeline("
    )
    expect(block).toContain("case_id: UUID = Query(")
    expect(block).toContain("reason: str = Body(")
    // `embed=True` is what makes the wrapped body above correct. Without it
    // FastAPI expects a bare JSON string and every admission fails validation.
    expect(block).toContain("embed=True")
  })

  it("still takes no account of what the router found", () => {
    // The route's whole signature, so a new parameter cannot be added without
    // this failing. A request that could name the finding could name a
    // convenient one, and the record would carry it as fact.
    const block = pythonBlock(
      routerSource,
      "async def admit_file_to_document_pipeline("
    )
    const signature = block.slice(0, block.indexOf("):"))
    for (const forbidden of [
      "route_outcome",
      "detected_format",
      "claimants",
      "file_name",
    ]) {
      expect(signature).not.toContain(forbidden)
    }
  })

  it("still turns only a missing file and a failed write into HTTP errors", () => {
    // Everything else -- including `refused` and `nothing_to_override` -- is a
    // fact about the file and comes back 200. If the backend started raising
    // on either, the answer this file is typed to read would never arrive and
    // the reason would surface as a browser error instead of beside the file.
    const respond = pythonBlock(routerSource, "def _respond_admission(")
    expect(respond).toContain("FileAdmissionOutcome.not_found")
    expect(respond).toContain("status_code=404")
    expect(respond).toContain("FileAdmissionOutcome.write_failed")
    expect(respond).toContain("status_code=500")

    const raised = [...respond.matchAll(/FileAdmissionOutcome\.(\w+)/g)].map(
      (m) => m[1]
    )
    expect(new Set(raised)).toEqual(new Set(["not_found", "write_failed"]))
  })

  it("still has exactly the outcomes this build knows how to read", () => {
    const members = enumMembers(
      serviceSource,
      "class FileAdmissionOutcome(str, Enum):"
    )
    expect(members.sort()).toEqual([...FILE_ADMISSION_OUTCOMES].sort())
  })

  it("still returns exactly the fields this build declares", () => {
    // Closed in both directions: a field added to the response and not read
    // here is dropped in silence, and a field dropped from the response leaves
    // this build reading `undefined` as though it were an answer.
    const keys = asDictKeys(serviceSource, "class FileAdmission:")
    expect(keys.sort()).toEqual([...FILE_ADMISSION_FIELDS].sort())
  })

  it("still names the two destinations this build displays", () => {
    // `routed_to` is derived from `admitted` on the backend, so the two cannot
    // disagree. These are the only two values it can hold.
    const admission = read(backend("services", "financial", "admission.py"))
    expect(admission).toContain('ROUTED_HELD = "held"')
    expect(admission).toContain('ROUTED_DOCUMENT_PIPELINE = "document_pipeline"')
  })

  it("still refuses under the error name this build looks for", () => {
    // The one string that tells this refusal apart from every other 409 the
    // API can return. If it changed, the reader would fall through to a
    // generic error and the admission would never be offered.
    const keys = asDictKeys(gateSource, "class UnadmittedFileError(Exception):")
    expect(keys.sort()).toEqual([...UNADMITTED_FILES_REFUSAL_FIELDS].sort())
    expect(gateSource).toContain(`"error": "${UNADMITTED_FILES_ERROR}"`)
  })

  it("still describes each held file with exactly the fields this build reads", () => {
    const keys = asDictKeys(gateSource, "class HeldFile:")
    expect(keys.sort()).toEqual([...HELD_FILE_FIELDS].sort())
  })

  it("still holds files back for exactly the findings this build can name", () => {
    // The route-check vocabulary is larger than this set: `not_found` and
    // `not_native` are outcomes too and neither holds anything back. Only
    // these four ever reach a refusal, so only these four need a reading.
    const routeCheck = read(backend("services", "financial", "route_check.py"))
    const declared = pythonBlock(routeCheck, "BLOCKING_OUTCOMES = frozenset(")
    const members = [...declared.matchAll(/"(\w+)"/g)].map((m) => m[1])
    expect(members.sort()).toEqual([...HELD_ROUTE_OUTCOMES].sort())
  })

  it("still refuses the whole request from every route that sends files", () => {
    // Three routes reach the gate. A route that stopped enforcing it would
    // send held material with no decision behind it, and nothing on this side
    // would notice: the request would simply succeed.
    const evidence = read(backend("routers", "evidence.py"))
    const folders = read(backend("routers", "evidence_folders.py"))

    expect(evidence).toContain("UnadmittedFileError")
    expect(folders).toContain("UnadmittedFileError")
    // Both of evidence.py's two, and the folder route's one.
    expect(
      [...evidence.matchAll(/status_code=409, detail=[a-z_]+\.as_dict\(\)/g)]
        .length
    ).toBe(2)
    expect(
      [...folders.matchAll(/status_code=409, detail=[a-z_]+\.as_dict\(\)/g)]
        .length
    ).toBe(1)
  })

  it("still calls the gate before anything is written", () => {
    // The gate is the last thing asked before the first thing is written, so
    // a refusal leaves the files exactly as it found them. If it moved below
    // `mark_processing`, a refused batch would be left marked as processing
    // with no job behind it, and the files would sit there forever.
    const processing = read(
      backend("services", "evidence_processing_service.py")
    )
    expect(processing.indexOf("gate_document_processing(")).toBeLessThan(
      processing.indexOf("EvidenceDBStorage.mark_processing(")
    )
  })
})
