import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { patternAPI, type Claim, type ClaimKind, type RoutineResponse, type Subject, type SubjectList } from "./api"
import { changedFields, inputFromClaim, KIND_WORDS } from "./claim-form-lib"
import { StatementCheckPanel } from "./components/StatementCheckPanel"
import { allowanceWords } from "./together-words"

vi.mock("./components/DraftPanel", () => ({ DraftPanel: () => null }))
vi.mock("./components/TextPlacePicker", () => ({ default: () => <div>map</div> }))

const subject: Subject = { kind: "extraction", extraction_id: "e1" }
const list = { extractions: [{ extraction_id: "e1", label: "Phone 1" }, { extraction_id: "e2", label: "Phone 2" }],
  dossiers: [{ dossier_id: "d1", name: "Person B" }], total_extractions: 2, total_dossiers: 1 } as unknown as SubjectList
const routine = { places: [{ cluster_id: 7, lat: 51.5, lon: -0.1, radius_m: 80.4, stay_count: 40, day_count: 21, routine: true, label: "Home",
  place_id: null, label_by: null, first_utc: "", last_utc: "" }], routine_places: [7] } as unknown as RoutineResponse

function claim(over: Partial<Claim> = {}): Claim {
  return { id: "c1", version: 1, status: "draft", status_words: "Not confirmed", kind: "inactive", subject, window_start: null, window_end: null,
    window_zone: null, window_text: null, place: null, activity: null, counterpart: null, origin: "manual", ai_model: null,
    missing_for_confirm: [], ...over }
}

/** The backend's missing_for_confirm (claims.py), so a test cannot reach Confirm on fields the server would refuse. */
function missing(c: Claim) {
  const out: string[] = []
  if (!c.window_start) out.push("window_start")
  if (!c.window_end) out.push("window_end")
  if (!c.window_zone) out.push("window_zone")
  if ((c.kind === "at_place" || c.kind === "not_at_place") && c.place?.lat == null) out.push("place")
  if (c.kind !== "inactive" && c.kind !== "active" && c.kind !== "at_place" && c.kind !== "not_at_place" && !c.counterpart) out.push("counterpart")
  return out
}

let stored: Claim[]
function server() {
  stored = []
  vi.spyOn(patternAPI, "claims").mockImplementation(async () => ({ total: stored.length, items: stored }))
  vi.spyOn(patternAPI, "subjects").mockResolvedValue(list)
  vi.spyOn(patternAPI, "routine").mockResolvedValue(routine)
  vi.spyOn(patternAPI, "createClaim").mockImplementation(async (_c, f) => {
    const c = claim({ id: `c${stored.length + 1}`, ...f } as Partial<Claim>)
    c.missing_for_confirm = missing(c)
    stored = [...stored, c]
    return c
  })
  vi.spyOn(patternAPI, "editClaim").mockImplementation(async (_c, id, f, v) => {
    const old = stored.find((c) => c.id === id) as Claim
    if (old.version !== v) throw new Error("Someone else changed this statement")
    const c = { ...old, ...f, version: v + 1 } as Claim
    c.missing_for_confirm = missing(c)
    stored = stored.map((x) => x.id === id ? c : x)
    return c
  })
  vi.spyOn(patternAPI, "confirmClaim").mockImplementation(async (_c, id) => {
    const c = { ...(stored.find((x) => x.id === id) as Claim), status: "confirmed" as const, status_words: "Confirmed" }
    stored = stored.map((x) => x.id === id ? c : x)
    return c
  })
  vi.spyOn(patternAPI, "evaluations").mockResolvedValue({ total: 0, items: [] })
  vi.spyOn(patternAPI, "evaluate").mockReturnValue(new Promise(() => {}))
}

function open() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><StatementCheckPanel caseId="k" subject={subject} /></MemoryRouter></QueryClientProvider>)
}

function fillWindow(root: HTMLElement) {
  fireEvent.change(within(root).getByLabelText("From (UTC)"), { target: { value: "2023-03-14T23:00" } })
  fireEvent.change(within(root).getByLabelText("Until (UTC)"), { target: { value: "2023-03-15T07:00" } })
}

beforeEach(server)
afterEach(() => vi.restoreAllMocks())

describe("every kind of statement can be completed", () => {
  it.each(Object.keys(KIND_WORDS) as ClaimKind[])("%s reaches Confirm through the form alone", async (kind) => {
    open()
    await screen.findByText("Statements for this phone or person (0)")
    const form = screen.getByText("Enter a statement").closest("details") as HTMLElement
    fireEvent.change(within(form).getByLabelText("What the statement says"), { target: { value: kind } })
    fillWindow(form)
    if (kind === "at_place" || kind === "not_at_place") {
      await within(form).findByRole("option", { name: /^Home/ })
      fireEvent.change(within(form).getByLabelText("A routine place of this phone or person"), { target: { value: "7" } })
    }
    if (kind === "with_subject" || kind === "apart_from_subject") {
      await within(form).findByRole("option", { name: "Phone 2" })
      fireEvent.change(within(form).getByLabelText("The other phone or person"), { target: { value: JSON.stringify({ kind: "extraction", extraction_id: "e2" }) } })
    }
    if (kind === "no_contact" || kind === "contact") {
      await within(form).findByRole("option", { name: "Person B (person)" })
      fireEvent.change(within(form).getByLabelText("The other person"), { target: { value: JSON.stringify({ kind: "dossier", dossier_id: "d1" }) } })
    }
    fireEvent.click(within(form).getByText("Save as not confirmed"))
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }))
    await waitFor(() => expect(patternAPI.confirmClaim).toHaveBeenCalledWith("k", "c1", 1))
    expect(screen.queryByText(/Settle before confirming/)).toBeNull()
  })

  it("sends a routine place as a point that keeps its cluster and name", async () => {
    open()
    const form = screen.getByText("Enter a statement").closest("details") as HTMLElement
    fireEvent.change(within(form).getByLabelText("What the statement says"), { target: { value: "at_place" } })
    await within(form).findByRole("option", { name: /^Home: 21 days, within 80 m/ })
    fireEvent.change(within(form).getByLabelText("A routine place of this phone or person"), { target: { value: "7" } })
    fireEvent.click(within(form).getByText("Save as not confirmed"))
    await waitFor(() => expect(patternAPI.createClaim).toHaveBeenCalled())
    expect(vi.mocked(patternAPI.createClaim).mock.calls[0][1].place).toEqual({ lat: 51.5, lon: -0.1, radius_m: 80, cluster_id: 7, label: "Home" })
  })

  it("finds an identity for contact, and says when the list is clipped", async () => {
    vi.spyOn(patternAPI, "identities").mockResolvedValue({ total: 31, items: [{ identity_id: "i9", identity_key: "phone:1", kind: "phone", value_display: "+1 555",
      names: [{ phone_label: "Phone 1", name: "Sam", basis: "contact" }], person: null, event_count: 12 }] })
    open()
    const form = screen.getByText("Enter a statement").closest("details") as HTMLElement
    fireEvent.change(within(form).getByLabelText("What the statement says"), { target: { value: "no_contact" } })
    fireEvent.change(within(form).getByLabelText("Find a name or number"), { target: { value: "sam" } })
    fireEvent.click(within(form).getByText("Find"))
    expect(await within(form).findByText(/Showing 1 of 31 found/)).toBeTruthy()
    fireEvent.click(within(form).getByText("Sam, +1 555 (12 events)"))
    fireEvent.click(within(form).getByText("Save as not confirmed"))
    await waitFor(() => expect(patternAPI.createClaim).toHaveBeenCalled())
    expect(vi.mocked(patternAPI.createClaim).mock.calls[0][1].counterpart).toEqual({ identity_ids: ["i9"], label: "Sam, +1 555 (12 events)" })
  })

  it("sends the tolerance in whole minutes on 'not using the phone' only", async () => {
    open()
    const form = screen.getByText("Enter a statement").closest("details") as HTMLElement
    fireEvent.change(within(form).getByLabelText(/Minutes of use to allow at each end/), { target: { value: "10" } })
    fireEvent.click(within(form).getByText("Save as not confirmed"))
    await waitFor(() => expect(patternAPI.createClaim).toHaveBeenCalled())
    expect(vi.mocked(patternAPI.createClaim).mock.calls[0][1].activity).toEqual({ tolerance_minutes: 10 })
    fireEvent.change(within(form).getByLabelText("What the statement says"), { target: { value: "active" } })
    expect(within(form).queryByLabelText(/Minutes of use to allow at each end/)).toBeNull()
  })
})

describe("settling a drafted statement", () => {
  const draft = () => claim({ origin: "ai_draft", ai_model: "deepseek", status_words: "Drafted by deepseek, not confirmed", kind: "at_place", window_text: "that evening",
    place: { text: "the flat" }, missing_for_confirm: ["window_start", "window_end", "window_zone", "place"],
    as_drafted: { kind: "at_place", window_text: "that evening", place_text: "the flat", counterpart_text: null, quote: "I was at the flat that evening" } })

  it("names what is missing in words and fills it through PATCH with the version, keeping the model's words", async () => {
    stored = [draft()]
    open()
    expect(await screen.findByText(/Settle before confirming: when it starts, when it ends, the time zone the statement uses, the place, as a routine place or a point\./)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Fill these in" }))
    const editor = screen.getByText("Save changes").closest("div.rounded") as HTMLElement
    expect(within(editor).getByText(/The draft says: "the flat"/)).toBeTruthy()
    fillWindow(editor)
    expect((within(editor).getByLabelText("Zone the statement uses") as HTMLInputElement).value).toBe("")  // a person chooses it
    fireEvent.change(within(editor).getByLabelText("Zone the statement uses"), { target: { value: "Europe/Dublin" } })
    await within(editor).findByRole("option", { name: /^Home/ })
    fireEvent.change(within(editor).getByLabelText("A routine place of this phone or person"), { target: { value: "7" } })
    fireEvent.click(within(editor).getByText("Save changes"))
    await waitFor(() => expect(patternAPI.editClaim).toHaveBeenCalled())
    const [, id, fields, version] = vi.mocked(patternAPI.editClaim).mock.calls[0]
    expect([id, version]).toEqual(["c1", 1])
    expect(fields).toEqual({ window_zone: "Europe/Dublin", window_start: "2023-03-14T23:00:00.000Z", window_end: "2023-03-15T07:00:00.000Z",
      place: { lat: 51.5, lon: -0.1, radius_m: 80, cluster_id: 7, label: "Home", text: "the flat" } })
    expect(await screen.findByRole("button", { name: "Confirm" })).toBeTruthy()
    expect(screen.getByText(/Drafted by deepseek as: At a place; "I was at the flat that evening"; time "that evening"; place "the flat"\./)).toBeTruthy()
    expect(screen.getByText("Drafted by deepseek, not confirmed")).toBeTruthy()
  })

  it("shows the refusal and reopens on the other person's version when the statement changed first", async () => {
    stored = [draft()]
    vi.mocked(patternAPI.editClaim).mockRejectedValueOnce(new Error("Someone else changed this statement while you were looking"))
    open()
    fireEvent.click(await screen.findByRole("button", { name: "Fill these in" }))
    const editor = screen.getByText("Save changes").closest("div.rounded") as HTMLElement
    fireEvent.change(within(editor).getByLabelText("The statement's own words"), { target: { value: "mine" } })
    fireEvent.click(within(editor).getByText("Save changes"))
    expect((await screen.findByRole("alert")).textContent).toMatch(/Someone else changed/)
    expect(patternAPI.claims).toHaveBeenCalledTimes(2)
  })
})

describe("an edit sends only what changed", () => {
  it("does not write a zone nobody chose, or touch a place when only the words change", () => {
    const c = claim({ kind: "at_place", window_text: "before", place: { lat: 1, lon: 2, radius_m: 30 } })
    const v = inputFromClaim(c)
    expect(v.zone).toBe("")
    expect(changedFields(c, { ...v, words: "after" })).toEqual({ window_text: "after" })
  })

  it("drops the routine place's name when its radius is changed by hand", async () => {
    open()
    await screen.findByText("Statements for this phone or person (0)")
    const form = screen.getByText("Enter a statement").closest("details") as HTMLElement
    fireEvent.change(within(form).getByLabelText("What the statement says"), { target: { value: "at_place" } })
    await within(form).findByRole("option", { name: /^Home/ })
    fireEvent.change(within(form).getByLabelText("A routine place of this phone or person"), { target: { value: "7" } })
    fireEvent.change(within(form).getByLabelText("Radius in metres"), { target: { value: "2000" } })
    fireEvent.click(within(form).getByText("Save as not confirmed"))
    await waitFor(() => expect(patternAPI.createClaim).toHaveBeenCalled())
    expect(vi.mocked(patternAPI.createClaim).mock.calls[0][1].place).toEqual({ lat: 51.5, lon: -0.1, radius_m: 2000 })
  })

  it("hides Confirm while the statement is open with changes not saved", async () => {
    stored = [claim({ window_start: "2023-03-14T23:00:00Z", window_end: "2023-03-15T07:00:00Z", window_zone: "UTC" })]
    open()
    await screen.findByRole("button", { name: "Confirm" })
    fireEvent.click(screen.getByRole("button", { name: "Edit" }))
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
  })

  it("leaves a stored time with seconds and a place's extra words alone", () => {
    const c = claim({ kind: "at_place", window_start: "2023-03-14T23:00:30+00:00", window_end: "2023-03-15T07:00:00+00:00", window_zone: "Europe/Dublin",
      window_text: "words", place: { lat: 1, lon: 2, radius_m: 30, text: "the flat" } })
    const v = inputFromClaim(c)
    expect(changedFields(c, v)).toEqual({})
    expect(changedFields(c, { ...v, words: "other" })).toEqual({ window_text: "other" })
  })

  it("keeps other activity options when the tolerance changes", () => {
    const c = claim({ window_zone: "UTC", activity: { tolerance_minutes: 5, what: "phone_use" } })
    expect(changedFields(c, { ...inputFromClaim(c), tolerance: "0" })).toEqual({ activity: { what: "phone_use" } })
  })
})

describe("Together's words come from the run", () => {
  it("states the run's own radius and speed", () => {
    expect(allowanceWords({ assumed_radius_m: 2500, max_speed_mps: 250 })).toEqual([
      "A position with no accuracy uses an assumed radius of 2,500 m and is marked.",
      "Two positions are separated only if travelling between them would take more than 900 km/h."])
    expect(allowanceWords(undefined)).toEqual([])
  })
})
