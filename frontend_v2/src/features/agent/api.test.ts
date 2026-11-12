import { afterEach, expect, it, vi } from "vitest"
import { agentAPI } from "./api"

afterEach(() => vi.unstubAllGlobals())

it("extracts an attached brief with an authenticated multipart request", async () => {
  const result = { filename: "template.docx", text: "Complete extracted brief", format: "docx", characters: 24, warnings: [] }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200, headers: { "Content-Type": "application/json" } }))
  vi.stubGlobal("fetch", fetchMock)
  const file = new File(["synthetic-document"], "template.docx")
  await expect(agentAPI.previewBrief(file)).resolves.toEqual(result)
  expect(fetchMock).toHaveBeenCalledWith("/api/agent/briefs/preview", expect.objectContaining({ method: "POST", credentials: "include", body: expect.any(FormData) }))
  expect(fetchMock.mock.calls[0][1].body.get("file").name).toBe("template.docx")
  expect(fetchMock.mock.calls[0][1].headers["Content-Type"]).toBeUndefined()
})

it("resumes the saved run using the resume endpoint without creating a new question", async () => {
  const event = { type: "status", message: "Resuming saved work" }
  const fetchMock = vi.fn().mockResolvedValue(new Response(`data: ${JSON.stringify(event)}\n\n`, { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  const receive = vi.fn()
  await agentAPI.streamMessage({ caseId: "case", threadId: "thread", message: "Continue", resumeRunId: "saved/run" }, receive)
  expect(fetchMock).toHaveBeenCalledWith("/api/agent/runs/saved%2Frun/resume", expect.objectContaining({ method: "POST", credentials: "include", body: undefined }))
  expect(receive).toHaveBeenCalledWith(event)
})

it("surfaces an unavailable checkpoint without silently starting another investigation", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "This historical run has no checkpoint. Retry its question." }), { status: 409 }))
  vi.stubGlobal("fetch", fetchMock)
  await expect(agentAPI.streamMessage({ caseId: "case", message: "Continue", resumeRunId: "old" }, vi.fn())).rejects.toThrow("historical run has no checkpoint")
  expect(fetchMock).toHaveBeenCalledTimes(1)
})
