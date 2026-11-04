import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  getMediaIndex: vi.fn().mockResolvedValue({ total: 2, no_time_count: 1, missing: 1, by_category: { Image: 2, Uncategorised: 1 }, verification: { match: 1, missing: 1, unchecked: 1 } }),
  getMediaWindow: vi.fn().mockResolvedValue({ offset: 0, limit: 200, items: [
    { file_uid: "f1", extraction_id: "e1", phone_label: "C1", category: "Image", filename: "synthetic-a.jpg", size: 10, taken_or_sent: { instant: null, full: "Tuesday, March 14, 2023 3:07 PM", basis: "message_time" }, verification: "match", verification_words: "Intact: matches its stated hash", missing: false, deleted_state: null, is_carved: false, message_count: 1, thumbnail_url: null },
    { file_uid: "f2", extraction_id: "e1", phone_label: "C1", category: "Image", filename: "synthetic-gone.jpg", size: null, taken_or_sent: { instant: null, full: "No time recorded", basis: "none" }, verification: "missing", verification_words: "The report refers to a file that is not in the production.", missing: true, deleted_state: null, is_carved: false, message_count: 0, thumbnail_url: null },
  ] }),
  getMediaDetail: vi.fn().mockResolvedValue({ file_uid: "f1", extraction_id: "e1", category: "Image", local_path: "chats/synthetic-a.jpg", size: 10, hashes: { sha256: "ab" }, verification: "match", verification_words: "Intact: matches its stated hash", missing: false, missing_words: null, deleted_state: null, is_carved: false, message_count: 1, messages: [{ record_uid: "a1", message_record_uid: "m1", kind: "message", instant: "2023-03-14T19:07:00Z", mechanism: "attachment_extracted_path", mechanism_words: "the attachment's extracted path" }] }),
  mediaObjectUrl: vi.fn().mockRejectedValue(new Error("not in a browser")),
  getDerivedTexts: vi.fn().mockResolvedValue({ file_uid: "f1", items: [] }),
  requestDerivedText: vi.fn().mockResolvedValue({ id: "d1", state: "queued" }),
  correctDerivedText: vi.fn().mockResolvedValue({ id: "d1", decision_id: "x" }),
  confirmDerivedText: vi.fn().mockResolvedValue({ id: "d1", decision_id: "y" }),
  describeDeriveBatch: vi.fn().mockResolvedValue({ kind: "transcript", in_scope: 0, eligible: 0, noun: "voice notes and videos", left_out: { already_read: 0, not_in_production: 0, empty_placeholder: 0 } }),
  getDeriveBatches: vi.fn().mockResolvedValue({ case_id: "c", items: [] }),
  acceptDerivedText: vi.fn().mockResolvedValue({ id: "a1", read_by: "Read by Whisper base 20250625, accepted by Synthetic Reviewer" }),
  getTranslations: vi.fn().mockResolvedValue({}),
  translateDerivedText: vi.fn(),
  describeImageIndex: vi.fn().mockResolvedValue({ images: 0, eligible: 0, indexed: 0, indexed_contents: 0, waiting: 0, left_out: { not_in_population: 0, not_in_production: 0, empty_placeholder: 0, could_not_open: 0, could_not_open_by_reason: {} }, uncategorised_files: 0, model_installed: true, model_words: null, model: "siglip2-base-patch16-224", model_id: "m", revision_short: "75de2d5", population_words: "" }),
  getImageIndexJobs: vi.fn().mockResolvedValue({ case_id: "c", items: [] }),
  getSettings: vi.fn().mockResolvedValue({ case_id: "c", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null, media_blur: { default_on: true, basis: "criminal_case", words: "On by default in a criminal case.", set: null } }),
  getMediaFacets: vi.fn().mockResolvedValue({ apps: [{ app: "SyntheticApp", files: 1 }], participants: [{ key: "phone:+12025550143", label: "Synthetic Contact", files: 1 }] }),
  getPhones: vi.fn().mockResolvedValue({ case_id: "c", total: 2, phones: [{ extraction_id: "e1", label: "C1" }, { extraction_id: "e2", label: "C2" }], case_zone: { name: "UTC", basis: "default", note: null } }),
  checkMediaDownload: vi.fn(),
  downloadMediaOriginals: vi.fn(),
}))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("../collect-targets", () => ({ useCollectTargets: () => ({ targets: [{ kind: "dossier", id: "p1", label: "Synthetic Person" }, { kind: "note", id: "n1", label: "A note" }], note: null, loading: false, error: null }) }))
import MediaPage, { DerivedTexts } from "./MediaPage"

describe("Media (03 section 8)", () => {
  it("states the total, shows a missing file as the sentence, and opens a file with the messages that carried it (M-1, M-2, M-4)", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media"]}>
          <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText(/^2 files\./)).toBeInTheDocument()
    const grid = await screen.findByRole("list", { name: "Files" })
    expect(await within(grid).findByText("synthetic-gone.jpg")).toBeInTheDocument()
    expect(within(grid).getAllByText("The report refers to a file that is not in the production.").length).toBeGreaterThan(0)
    expect(within(grid).queryByRole("img", { name: "synthetic-gone.jpg" })).toBeNull()
    fireEvent.click(within(grid).getByText("synthetic-a.jpg"))
    const panel = await screen.findByRole("complementary", { name: "File" })
    expect(await within(panel).findByText("Carried by 1 message")).toBeInTheDocument()
    expect(within(panel).getByText(/found by the attachment's extracted path/)).toBeInTheDocument()
    expect(within(panel).getByRole("link", { name: /The message at/ })).toHaveAttribute("href", "/cases/c/records/m1")
  })

  it("scoped to a thread from its Attachments (N): the scope is shown, Previous and Next step the files, Back to the stream returns (MD-1)", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={[`/cases/c/phones/e1/records/media?${new URLSearchParams({ thread: "t1", thread_title: "Synthetic thread", back: "/cases/c/phones/e1/records/conversations?thread=t1&at=ev9" })}`]}>
          <Routes>
            <Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} />
            <Route path="/cases/:id/phones/:extraction/records/conversations" element={<p>the stream</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText(/Files carried by the conversation "Synthetic thread"/)).toBeInTheDocument()
    await waitFor(() => expect(api.getMediaIndex).toHaveBeenCalledWith({ case_id: "c", phones: ["e1"], thread_key: "t1" }))
    expect(api.getMediaWindow).toHaveBeenCalledWith({ case_id: "c", phones: ["e1"], thread_key: "t1" }, 0, expect.any(Number))
    const grid = await screen.findByRole("list", { name: "Files" })
    fireEvent.click(await within(grid).findByText("synthetic-a.jpg"))
    const panel = await screen.findByRole("complementary", { name: "File" })
    expect(within(panel).getByRole("heading", { name: "File 1 of 2" })).toBeInTheDocument()
    expect(within(panel).getByRole("button", { name: "Previous" })).toBeDisabled()
    fireEvent.click(within(panel).getByRole("button", { name: "Next" }))
    expect(await within(screen.getByRole("complementary", { name: "File" })).findByRole("heading", { name: "File 2 of 2" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("link", { name: "Back to the stream" }))
    expect(await screen.findByText("the stream")).toBeInTheDocument()
  })

  it("opens the file named in the address, asks for its text, and shows the result labelled machine-generated beside the original (M-3)", async () => {
    api.getDerivedTexts
      .mockResolvedValueOnce({ file_uid: "f1", items: [] })
      .mockResolvedValue({ file_uid: "f1", items: [{ id: "d1", file_uid: "f1", kind: "ocr", state: "done", text: "SYNTHETIC HARBOUR NOTICE", model: "Tesseract", model_version: "5.5.0", segments: [], error: null, created_at: null, finished_at: null, machine_generated: true, label: "Machine-generated by Tesseract 5.5.0 on Tuesday, November 3, 2026. The original is above.", model_id: "tesseract/eng", weights_sha256: "a".repeat(64), input_sha256: "b".repeat(64), parameters: { languages: "eng" }, provider: "local", provider_words: "Made on this server. Nothing was sent to any outside service.", sniffed_container: "jpeg" }] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media?file=f1"]}>
          <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const panel = await screen.findByRole("complementary", { name: "File" })
    const derived = await within(panel).findByRole("region", { name: "Machine-generated text" })
    fireEvent.click(within(derived).getByRole("button", { name: "Read text in this image" }))
    expect(api.requestDerivedText).toHaveBeenCalledWith("c", "f1", "ocr")
    expect(await within(derived).findByText("SYNTHETIC HARBOUR NOTICE")).toBeInTheDocument()
    expect(within(derived).getByText(/^Machine-generated by Tesseract 5\.5\.0 on .*The original is above\.$/)).toBeInTheDocument()
    // 05 17.4: the setting it was made under, and exactly what made it, with the hashes in full
    expect(within(derived).getByText("Made on this server. Nothing was sent to any outside service.")).toBeInTheDocument()
    expect(within(derived).getByText("What made this text")).toBeInTheDocument()
    expect(within(derived).getByText("tesseract/eng (5.5.0)")).toBeInTheDocument()
    expect(within(derived).getByText("a".repeat(64))).toBeInTheDocument()
    expect(within(derived).getByText("b".repeat(64))).toBeInTheDocument()
  })

  it("offers both readings for a file the report left uncategorised, and says its contents decide (05 17.4)", async () => {
    api.getDerivedTexts.mockResolvedValue({ file_uid: "f9", items: [] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <DerivedTexts caseId="c" fileUid="f9" category="Uncategorized" />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("The report does not say what kind of file this is; its contents decide which reading works.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Transcribe this audio" }))
    expect(api.requestDerivedText).toHaveBeenCalledWith("c", "f9", "transcript")
    expect(screen.getByRole("button", { name: "Read text in this image" })).toBeInTheDocument()
  })

  it("corrects machine text with a reason, keeps the machine original shown, and confirms it (07 4.6, M-6)", async () => {
    const base = { id: "d1", file_uid: "f9", kind: "transcript" as const, state: "done" as const, text: "SYNTHETIC MACHINE WORDS", model: "Whisper", model_version: "base 20250625", segments: [], error: null, created_at: null, finished_at: null, machine_generated: true as const, label: "Machine-generated by Whisper base 20250625 on Tuesday, November 3, 2026. The original is above." }
    api.getDerivedTexts.mockResolvedValue({ file_uid: "f9", items: [{ ...base, effective_text: base.text, origin: { state: "machine", confirmed: false, words: "Machine-generated by Whisper base 20250625 on Tuesday, November 3, 2026, not yet confirmed" } }] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <DerivedTexts caseId="c" fileUid="f9" category="Audio" />
      </QueryClientProvider>,
    )
    expect(await screen.findByText(/not yet confirmed$/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "I checked it against the audio: confirm" }))
    await waitFor(() => expect(api.confirmDerivedText).toHaveBeenCalledWith("c", "d1"))
    fireEvent.click(screen.getByRole("button", { name: "Correct this text" }))
    const save = screen.getByRole("button", { name: "Save correction" })
    fireEvent.change(screen.getByRole("textbox", { name: "Corrected text" }), { target: { value: "SYNTHETIC PERSON WORDS" } })
    expect(save).toBeDisabled() // a correction needs a reason
    api.getDerivedTexts.mockResolvedValue({ file_uid: "f9", items: [{ ...base, corrected_text: "SYNTHETIC PERSON WORDS", effective_text: "SYNTHETIC PERSON WORDS", origin: { state: "corrected", confirmed: true, words: "Corrected by Synthetic Reviewer on Tuesday, November 3, 2026: heard it" } }] })
    fireEvent.change(screen.getByRole("textbox", { name: "Reason, in your own words" }), { target: { value: "heard it" } })
    fireEvent.click(save)
    await waitFor(() => expect(api.correctDerivedText).toHaveBeenCalledWith("c", "d1", "SYNTHETIC PERSON WORDS", "heard it"))
    expect(await screen.findByText("Corrected by Synthetic Reviewer on Tuesday, November 3, 2026: heard it")).toBeInTheDocument()
    expect(screen.getByText("SYNTHETIC PERSON WORDS")).toBeInTheDocument()
    expect(screen.getByText("SYNTHETIC MACHINE WORDS")).toBeInTheDocument() // the machine original stays shown
    expect(screen.getByText("Machine original, kept as it was read")).toBeInTheDocument()
  })

  it("uses an unconfirmed transcript in a dossier assessment only after it is confirmed or kept marked, as AI-assisted (CO-18, M-7)", async () => {
    api.mediaObjectUrl.mockResolvedValue({ url: "blob:synthetic", type: "audio/ogg" })
    api.getDerivedTexts.mockResolvedValue({ file_uid: "f9", items: [{ id: "d1", file_uid: "f9", kind: "transcript", state: "done", text: "SYNTHETIC MACHINE WORDS", model: "Whisper", model_version: "base 20250625", segments: [], error: null, created_at: null, finished_at: null, machine_generated: true, label: "Machine-generated by Whisper base 20250625.", effective_text: "SYNTHETIC MACHINE WORDS", origin: { state: "machine", confirmed: false, words: "Machine-generated by Whisper base 20250625 on Tuesday, November 3, 2026, not yet confirmed" } }] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <DerivedTexts caseId="c" fileUid="f9" category="Audio" filename="synthetic-note.ogg" />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole("button", { name: "Use in a dossier assessment" }))
    expect(screen.getByText("This transcript is machine-generated. Listen and confirm, or keep it marked.")).toBeInTheDocument()
    expect(await screen.findByLabelText("Listen to synthetic-note.ogg")).toHaveAttribute("src", "blob:synthetic")
    expect(within(screen.getByRole("combobox", { name: "Dossier" })).queryByRole("option", { name: "A note" })).toBeNull()
    fireEvent.change(screen.getByRole("combobox", { name: "Dossier" }), { target: { value: "p1" } })
    const add = screen.getByRole("button", { name: "Add to the assessment" })
    expect(add).toBeDisabled() // the prompt needs an answer first
    fireEvent.click(screen.getByRole("button", { name: "Keep it marked" }))
    expect(add).toBeEnabled()
    fireEvent.click(add)
    await waitFor(() => expect(api.acceptDerivedText).toHaveBeenCalledWith("c", "d1", "p1", "Statement"))
    expect(await screen.findByText("Added to the dossier: Read by Whisper base 20250625, accepted by Synthetic Reviewer")).toBeInTheDocument()
  })

  it("shows a voice note's transcript mark in the grid and plays it there (M-transcript)", async () => {
    api.getMediaWindow.mockResolvedValueOnce({ offset: 0, limit: 200, items: [
      { file_uid: "v1", extraction_id: "e1", phone_label: "C5", category: "Audio", filename: "PTT-00001.opus", size: 10, taken_or_sent: { instant: null, full: "No time recorded", basis: "none" }, verification: "match", verification_words: "Intact: matches its stated hash", missing: false, deleted_state: null, is_carved: false, message_count: 1, thumbnail_url: null,
        machine_text: [{ kind: "transcript", state: "machine", short: "Machine-generated", words: "Machine-generated by Whisper base 20250625 on Tuesday, November 3, 2026, not yet confirmed" }] },
    ] })
    api.mediaObjectUrl.mockResolvedValue({ url: "blob:synthetic", type: "audio/ogg" })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media"]}>
          <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const grid = await screen.findByRole("list", { name: "Files" })
    const mark = await within(grid).findByText("Transcript: Machine-generated")
    expect(mark).toHaveAttribute("title", expect.stringMatching(/not yet confirmed$/))
    fireEvent.click(within(grid).getByRole("button", { name: "Play PTT-00001.opus" }))
    expect(await within(grid).findByLabelText("Listen to PTT-00001.opus")).toHaveAttribute("src", "blob:synthetic")
  })

  it("filters to files with no category or no check by sending an empty value, not All", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media"]}>
          <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const cat = await screen.findByRole("combobox", { name: /Category/ })
    await within(cat).findByRole("option", { name: "Uncategorised (1)" })
    fireEvent.change(cat, { target: { value: within(cat).getByRole("option", { name: "Uncategorised (1)" }).getAttribute("value") } })
    await waitFor(() => expect(api.getMediaIndex).toHaveBeenCalledWith(expect.objectContaining({ categories: [""] })))
    const st = screen.getByRole("combobox", { name: /State/ })
    fireEvent.change(st, { target: { value: within(st).getByRole("option", { name: "unchecked (1)" }).getAttribute("value") } })
    await waitFor(() => expect(api.getMediaIndex).toHaveBeenCalledWith(expect.objectContaining({ categories: [""], verification: [""] })))
  })

  it("a visible tile asks for the server's small preview; opening the file asks for the original", async () => {
    const seen = vi.fn()
    vi.stubGlobal("IntersectionObserver", class {
      cb: (e: { isIntersecting: boolean }[]) => void
      constructor(cb: (e: { isIntersecting: boolean }[]) => void) {
        this.cb = cb
      }
      observe() {
        seen()
        this.cb([{ isIntersecting: true }])
      }
      disconnect() {}
    })
    api.mediaObjectUrl.mockClear()
    try {
      render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media"]}>
            <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      )
      const grid = await screen.findByRole("list", { name: "Files" })
      await waitFor(() => expect(api.mediaObjectUrl).toHaveBeenCalledWith("c", "f1", expect.anything(), "thumbnail"))
      // the missing file is never fetched
      expect(api.mediaObjectUrl.mock.calls.some((c) => c[1] === "f2")).toBe(false)
      fireEvent.click(within(grid).getByText("synthetic-a.jpg"))
      await waitFor(() => expect(api.mediaObjectUrl.mock.calls.some((c) => c[1] === "f1" && c[3] === "content")).toBe(true))
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it.each([
    ["an error", (v: HTMLVideoElement) => fireEvent.error(v)],
    ["no picture after loading", (v: HTMLVideoElement) => {
      Object.defineProperty(v, "videoWidth", { value: 0, configurable: true })
      fireEvent.loadedData(v)
    }],
  ])("a video the browser cannot play on %s is played from a converted copy, and says so (03 8.3, 03 20.5)", async (_why, fail) => {
    api.getMediaDetail.mockResolvedValueOnce({ file_uid: "f1", extraction_id: "e1", category: "Video", local_path: "chats/synthetic-clip.ts", size: 10, hashes: {}, verification: "match", verification_words: "Intact: matches its stated hash", missing: false, missing_words: null, deleted_state: null, is_carved: false, message_count: 0, messages: [] })
    api.mediaObjectUrl.mockReset()
    api.mediaObjectUrl.mockImplementation((_c: string, _f: string, _s: AbortSignal, variant: string) =>
      Promise.resolve(variant === "converted" ? { url: "blob:converted", type: "video/mp4" } : variant === "content" ? { url: "blob:original", type: "video/mp2t" } : Promise.reject(new Error("no thumbnail"))))
    try {
      render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media"]}>
            <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      )
      const grid = await screen.findByRole("list", { name: "Files" })
      fireEvent.click(await within(grid).findByText("synthetic-a.jpg"))
      const panel = await screen.findByRole("complementary", { name: "File" })
      await waitFor(() => expect(panel.querySelector("video")).toHaveAttribute("src", "blob:original"))
      expect(within(panel).queryByText("Playing a converted copy. The original file is unchanged.")).toBeNull()
      fail(panel.querySelector("video") as HTMLVideoElement)
      await waitFor(() => expect(panel.querySelector("video")).toHaveAttribute("src", "blob:converted"))
      expect(within(panel).getByText("Playing a converted copy. The original file is unchanged.")).toBeInTheDocument()
      expect(within(panel).getByRole("link", { name: "Save the original" })).toHaveAttribute("href", "blob:original")
      expect(api.mediaObjectUrl.mock.calls.filter((c) => c[3] === "converted")).toHaveLength(1)
    } finally {
      api.mediaObjectUrl.mockReset()
      api.mediaObjectUrl.mockRejectedValue(new Error("not in a browser"))
    }
  })

  it("translates a transcript on the server and shows the translation under it, segment by segment, labelled (05 17.5)", async () => {
    const seg = [{ start: 0, end: 2.5, text: "SINTETICO PALABRAS UNO" }]
    api.getDerivedTexts.mockResolvedValue({ file_uid: "f9", items: [{ id: "d7", file_uid: "f9", kind: "transcript", state: "done", text: "SINTETICO PALABRAS UNO", model: "Whisper", model_version: "base 20250625", segments: seg, error: null, created_at: null, finished_at: null, machine_generated: true, label: "Machine-generated by Whisper base 20250625.", effective_text: "SINTETICO PALABRAS UNO", origin: { state: "machine", confirmed: false, words: "Machine-generated, not yet confirmed" } }] })
    api.getTranslations.mockResolvedValue({})
    api.translateDerivedText.mockResolvedValue({ id: "t1", source_type: "derived_text", source_key: "d7", state: "done", outcome: "translated", text: "SYNTHETIC WORDS ONE", segments: [{ start: 65, end: 67, source: "SINTETICO PALABRAS UNO", text: "SYNTHETIC WORDS ONE" }], error: null, detected_language: "es", detected_language_name: "Spanish", detected_confidence: 0.9, model: "opus-mt-es-en", model_id: "Helsinki-NLP/opus-mt-es-en@c96e2c5", model_version: "c96e2c5, transformers 5.3.0", weights_sha256: "a".repeat(64), label: "Machine translation (local, opus-mt-es-en c96e2c5, transformers 5.3.0), not checked by a person. The original is above.", language_words: "Language identified by lingua 2.1.1 as Spanish (confidence 90%).", outcome_words: null, provider_words: "Made on this server. Nothing was sent to any outside service.", stale: false, stale_words: null, machine_generated: true })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <DerivedTexts caseId="c" fileUid="f9" category="Audio" />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole("button", { name: "Translate this transcript" }))
    await waitFor(() => expect(api.translateDerivedText).toHaveBeenCalledWith("c", "d7"))
    const translated = await screen.findByText("SYNTHETIC WORDS ONE")
    expect(translated.closest("li")?.textContent).toBe("1:05 SYNTHETIC WORDS ONE")
    expect(screen.getByText(/^Machine translation \(local, opus-mt-es-en c96e2c5, transformers 5\.3\.0\), not checked by a person\./)).toBeInTheDocument()
    expect(screen.getByText("Machine translation from Spanish")).toBeInTheDocument()
    // the original is shown first, the translation under it
    const original = screen.getByText("SINTETICO PALABRAS UNO")
    expect(original.compareDocumentPosition(translated) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Translate this transcript" })).not.toBeInTheDocument()
  })

  it("after a person corrects a translated transcript, its translation shows as made from an earlier text (05 17.5)", async () => {
    const item = { id: "d8", file_uid: "f9", kind: "transcript", state: "done", text: "SINTETICO DOS", model: "Whisper", model_version: "base 20250625", segments: [], error: null, created_at: null, finished_at: null, machine_generated: true, label: "Machine-generated by Whisper base 20250625.", effective_text: "SINTETICO DOS", origin: { state: "machine", confirmed: false, words: "Machine-generated, not yet confirmed" } }
    const done = { id: "t2", source_type: "derived_text", source_key: "d8", state: "done", outcome: "translated", text: "SYNTHETIC TWO", segments: [], error: null, detected_language: "es", detected_language_name: "Spanish", detected_confidence: 0.9, model: "opus-mt-es-en", model_id: null, model_version: "c96e2c5, transformers 5.3.0", weights_sha256: null, label: "Machine translation (local, opus-mt-es-en c96e2c5, transformers 5.3.0), not checked by a person. The original is above.", language_words: null, outcome_words: null, provider_words: null, stale: false, stale_words: null, machine_generated: true }
    api.getDerivedTexts.mockResolvedValue({ file_uid: "f9", items: [item] })
    api.getTranslations.mockResolvedValue({ d8: done })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <DerivedTexts caseId="c" fileUid="f9" category="Audio" />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("SYNTHETIC TWO")).toBeInTheDocument()
    // the person's correction is saved; the panel reads the machine texts again
    api.getDerivedTexts.mockResolvedValue({ file_uid: "f9", items: [{ ...item, corrected_text: "SINTETICO TRES", effective_text: "SINTETICO TRES", origin: { state: "corrected", confirmed: true, words: "Corrected by Synthetic Reviewer" } }] })
    api.getTranslations.mockResolvedValue({ d8: { ...done, stale: true, stale_words: "Made from an earlier text: the original has been corrected since." } })
    await client.invalidateQueries({ queryKey: ["phone-media-derived", "c", "f9"] })
    expect(await screen.findByText("Made from an earlier text: the original has been corrected since.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Translate the corrected transcript" })).toBeInTheDocument()
  })
})

describe("Media viewer tools (03 8.3)", () => {
  const page = (entry = "/cases/c/phones/e1/records/media") => render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes><Route path="/cases/:id/phones/:extraction/records/media" element={<MediaPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )

  it("moves to the next and previous file with the buttons and the arrow keys", async () => {
    localStorage.clear()
    page("/cases/c/phones/e1/records/media?file=f1")
    const panel = await screen.findByRole("complementary", { name: "File" })
    expect(await within(panel).findByText(/File 1 of 2/)).toBeInTheDocument()
    expect(within(panel).getByRole("button", { name: "Previous" })).toBeDisabled()
    fireEvent.keyDown(window, { key: "ArrowRight" })
    expect(await within(panel).findByText(/File 2 of 2/)).toBeInTheDocument()
    expect(within(panel).getByRole("button", { name: "Next" })).toBeDisabled()
    fireEvent.click(within(panel).getByRole("button", { name: "Previous" }))
    expect(await within(panel).findByText(/File 1 of 2/)).toBeInTheDocument()
  })

  it("filters by app, person and dates, sending them to the server", async () => {
    localStorage.clear()
    page()
    const app = await screen.findByRole("combobox", { name: /App/ })
    await screen.findByRole("option", { name: "SyntheticApp (1)" })
    fireEvent.change(app, { target: { value: "SyntheticApp" } })
    fireEvent.change(screen.getByRole("combobox", { name: /Person/ }), { target: { value: "phone:+12025550143" } })
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2023-03-14" } })
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2023-03-14" } })
    await waitFor(() => expect(api.getMediaIndex).toHaveBeenCalledWith(expect.objectContaining({
      apps: ["SyntheticApp"], participants: ["phone:+12025550143"],
      from_instant: "2023-03-14T00:00:00.000Z", to_instant: "2023-03-15T00:00:00.000Z" })))
    expect(screen.getByText(/whole days in UTC/)).toBeInTheDocument()
    const phones = screen.getByRole("combobox", { name: /Phones/ })
    await screen.findByRole("option", { name: "C2" })
    expect(screen.queryByRole("option", { name: "C1" })).toBeNull()  // this phone is the first choice
    fireEvent.change(phones, { target: { value: "*" } })
    await waitFor(() => expect(api.getMediaFacets).toHaveBeenLastCalledWith({ case_id: "c" }))
    fireEvent.change(phones, { target: { value: "e2" } })
    await waitFor(() => expect(api.getMediaIndex).toHaveBeenLastCalledWith(expect.objectContaining({ phones: ["e2"] })))
  })

  it("blurs by the case default until the person chooses, and changes the thumbnail size", async () => {
    localStorage.clear()
    page()
    const box = await screen.findByRole("checkbox", { name: "Blur pictures until opened" })
    await screen.findByText(/On by default in a criminal case/)
    expect(box).toBeChecked()
    api.getSettings.mockResolvedValueOnce({ case_id: "c", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null, media_blur: { default_on: false, basis: "not_criminal", words: "Off by default: this is not a criminal case.", set: null } })
    fireEvent.click(box)
    expect(localStorage.getItem("loupe.media.blur")).toBe("off")
    const size = screen.getByRole("combobox", { name: /Thumbnails/ })
    fireEvent.change(size, { target: { value: "large" } })
    expect(screen.getByRole("list", { name: "Files" }).className).toContain("14rem")
    expect(localStorage.getItem("loupe.media.thumb")).toBe("large")
  })

  it("copies the chosen files' list without the clipboard API, and says when only some are loaded", async () => {
    localStorage.clear()
    const exec = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true })
    page()
    fireEvent.click(await screen.findByRole("checkbox", { name: "Choose synthetic-a.jpg" }))
    fireEvent.click(screen.getByRole("button", { name: "Copy file list" }))
    expect(exec).toHaveBeenCalledWith("copy")
    expect(screen.getByText("Copied the list of 1 chosen file.")).toBeInTheDocument()
    exec.mockReturnValue(false)
    fireEvent.click(screen.getByRole("button", { name: "Clear the choice" }))
    fireEvent.click(screen.getByRole("button", { name: "Copy file list" }))
    expect(screen.getByText(/did not allow copying. The list of all 2 files is below/)).toBeInTheDocument()
    expect((screen.getByRole("textbox", { name: "File list to copy" }) as HTMLTextAreaElement).value).toMatch(/^File\tPhone\tCategory\tTime\tState\tSHA-256\tMD5\nsynthetic-a.jpg\tC1\tImage\t/)
  })

  it("shows a refused download with its numbers and makes nothing", async () => {
    localStorage.clear()
    api.checkMediaDownload.mockResolvedValueOnce({ count: 3000, held: 3000, not_in_production: 0, bytes: 5, refusal: "These 3,000 files are 1 MB. A download holds at most 2,000 files and 1.0 GB, so nothing was made. Choose fewer (a phone, a category or dates) and download again.", max_files: 2000, max_bytes: 1 })
    page()
    const dl = await screen.findByRole("button", { name: "Download originals" })
    await waitFor(() => expect(dl).toBeEnabled())
    fireEvent.click(dl)
    expect(await screen.findByRole("alert")).toHaveTextContent("so nothing was made")
    expect(api.downloadMediaOriginals).not.toHaveBeenCalled()
    expect(screen.queryByRole("button", { name: "Download the zip" })).toBeNull()
  })

  it("downloads the chosen originals after stating what the zip holds", async () => {
    localStorage.clear()
    api.checkMediaDownload.mockResolvedValueOnce({ count: 2, held: 1, not_in_production: 1, bytes: 2048, refusal: null, max_files: 2000, max_bytes: 1 })
    api.downloadMediaOriginals.mockResolvedValueOnce({ blob: new Blob(["z"]), files: 2 })
    const made = vi.fn().mockReturnValue("blob:x")
    Object.defineProperty(URL, "createObjectURL", { value: made, configurable: true })
    page()
    const dl = await screen.findByRole("button", { name: "Download originals" })
    await waitFor(() => expect(dl).toBeEnabled())
    fireEvent.click(dl)
    expect(await screen.findByText(/2 files, 2 KB, as a zip with manifest.csv/)).toBeInTheDocument()
    expect(screen.getByText(/1 the report names are not in the production/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Download the zip" }))
    expect(await screen.findByText("Downloaded 2 files with manifest.csv of their hashes.")).toBeInTheDocument()
    expect(made).toHaveBeenCalled()
  })
})
