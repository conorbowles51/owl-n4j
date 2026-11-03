import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { StreamRow, Translation } from "../schemas"

const api = vi.hoisted(() => ({ translateMessage: vi.fn(), getTranslations: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
import { MessageTranslation } from "./MessageTranslation"

const row = (over: Partial<StreamRow> = {}): StreamRow =>
  ({
    event_uid: "ev1", record_uid: "r1", kind: "message", phone: { extraction_id: "e1", label: "C1" }, app: "WhatsApp", thread: null,
    direction: "incoming", time: {} as StreamRow["time"], from: null, to: [], body: "Trae el paquete sintético.", subject: null, call: null,
    attachments: [], flags: [], copies: { count: 1, record_uids: ["r1"], apps: ["WhatsApp"] }, owner_read: { date_read: null, date_played: null },
    interpretation_level: "reviewed", line: "", ...over,
  }) as StreamRow

const base: Translation = {
  id: "t1", source_type: "message", source_key: "ev1", state: "queued", outcome: null, text: null, segments: [], error: null,
  detected_language: null, detected_language_name: null, detected_confidence: null, model: null, model_id: null, model_version: null,
  weights_sha256: null, label: null, language_words: null, outcome_words: null, provider_words: null, stale: false, stale_words: null,
  machine_generated: true,
}
const done: Translation = {
  ...base, state: "done", outcome: "translated", text: "Bring the synthetic package.", detected_language: "es", detected_language_name: "Spanish",
  detected_confidence: 0.93, model: "opus-mt-es-en", model_version: "c96e2c5, transformers 5.3.0",
  label: "Machine translation (local, opus-mt-es-en c96e2c5, transformers 5.3.0), not checked by a person. The original is above.",
  language_words: "Language identified by lingua 2.1.1 as Spanish (confidence 93%).",
}

const show = (r: StreamRow) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <p>{r.body}</p>
      <MessageTranslation caseId="c" row={r} />
    </QueryClientProvider>,
  )

describe("MessageTranslation (05 17.5)", () => {
  it("asks for a translation, says it is waiting, and shows it under the original with its label and language", async () => {
    api.translateMessage.mockResolvedValue(base)
    api.getTranslations.mockResolvedValue({ ev1: done })
    show(row())
    fireEvent.click(screen.getByRole("button", { name: "Translate" }))
    await waitFor(() => expect(api.translateMessage).toHaveBeenCalledWith("c", "ev1"))
    expect(await screen.findByText("Waiting to be translated on this server.")).toBeInTheDocument()
    const t = await screen.findByText("Bring the synthetic package.", {}, { timeout: 6000 })
    expect(api.getTranslations).toHaveBeenCalledWith("c", "message", ["ev1"])
    expect(screen.getByText(done.label!)).toBeInTheDocument()
    expect(screen.getByText(done.language_words!)).toBeInTheDocument()
    const original = screen.getByText("Trae el paquete sintético.")
    expect(original.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Translate" })).not.toBeInTheDocument()
  }, 10000)

  it("says a message in English or not recognised was not translated, and invents nothing", () => {
    show(row({ translation: { ...base, state: "done", outcome: "already_english", outcome_words: "Already in English; not translated.", language_words: "Language identified by lingua 2.1.1 as English (confidence 97%)." } }))
    expect(screen.getByText(/^Already in English; not translated\./)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Translate" })).not.toBeInTheDocument()
  })

  it("shows a translation of an earlier text as such and offers to translate the corrected text", () => {
    show(row({ translation: { ...done, stale: true, stale_words: "Made from an earlier text: the original has been corrected since." } }))
    expect(screen.getByText("Made from an earlier text: the original has been corrected since.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Translate the corrected text" })).toBeInTheDocument()
  })

  it("states a refusal in the server's words and shows nothing for a message with no text", () => {
    const { container } = show(row({ body: null }))
    expect(container.querySelector("[data-testid=message-translation]")).toBeNull()
    show(row({ event_uid: "ev2", translation: { ...base, source_key: "ev2", state: "failed", error: "No Spanish to English translation model is installed on this server. Nothing was sent anywhere." } }))
    expect(screen.getByRole("alert")).toHaveTextContent("No Spanish to English translation model is installed on this server.")
    expect(screen.getByRole("button", { name: "Try translating again" })).toBeInTheDocument()
  })
})
