/// <reference types="node" />
import fs from "node:fs"
import path from "node:path"
import { useState, type ReactNode } from "react"
import { act, fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { Dialog, DialogContent } from "@/components/ui/dialog"
import { FEATURES } from "../feature-list"
import { AREA_GUIDE, GUIDES } from "../guides"
import { stepsShown, workflowsShown } from "./available"
import { CASE_KINDS, CATALOGUE, QUESTIONS } from "./catalogue"
import { TUTORIALS } from "./tutorials"
import type { Workflow } from "./types"
import { StepReturn, Tutorial, WorkflowList } from "./WorkflowGuide"

const front = path.resolve(__dirname, "../../../..")
const src = path.join(front, "src")
const img = path.join(front, "public/docs/workflows/img")

/**
 * Every feature in the guidance feature list (feature-list.ts) appears in at least one workflow's `features`, by id;
 * EXCEPTIONS says why one does not: each is a screen detail met inside a workflow, or a way of getting around the app,
 * and its guide section explains it.
 */
const EXCEPTIONS: Record<string, string> = {
  "start-here": "Start here is a way into the workflows: each of its steps opens one with Show me how.",
  "guide-menu": "The Guide menu is where the workflows open; it is not a step of one.",
  "step-history": "The bottom bar of your steps is how you get back to a screen, on every workflow alike.",
  "case-settings": "Case settings are set once per case, not part of following a question.",
  "evidence-send-locked": "A send that cannot start says why on the screen itself; Bring in the evidence meets it only when a send is refused.",
  "unchecked-claims": "Unchecked claims sit on one file's page; the evidence guide explains them.",
  "text-workbench": "The text reader is how one document is read, not a question followed across the case.",
  "document-dates": "Dates read from a document show on that document's page; the evidence guide explains them.",
  "timeline-undated": "Events with no time recorded are listed apart on the Timeline; the timeline guide explains them.",
  "map-review": "Places that need review are a check on the map's addresses, not a step of a workflow.",
  "record-panel-sheet": "How a phone record opens over the page, on every phone workflow alike.",
  "changed-since-cited": "Changed since cited shows on a theory only after its evidence changes; the theories guide explains it.",
  "graph-overlap": "Behind the new Corroborate; the Graph guide explains it.",
  "also-elsewhere": "Behind the new Corroborate; a mark in Conversations that the phones guide explains.",
  "corroborate-panel": "Behind the new Corroborate; the Corroborate guide explains the panel over the page.",
  "lead-records": "Behind the new Corroborate; a button on each lead that the Corroborate guide explains.",
  "around-event": "Behind the new Corroborate; the Corroborate guide explains Money around an event.",
  "who-overlaps": "Behind the new Corroborate; the Corroborate guide explains Who overlaps with whom.",
  "area-compare": "Behind the new Corroborate; the Corroborate guide explains comparing drawn areas.",
  "search-notifications": "What search reads, not a control; Search the whole case uses it.",
  "dossier-addresses": "Map positions of a dossier's addresses show inside the dossier; the dossiers guide explains them.",
  "phones-together":
    "Behind the phone-together setting, which is off; the phones guide explains it. Phone patterns' Together view, which every case has, is in Was he there? and the staged-accident workflow.",
  "chat": "AI chat answers short questions beside a screen; the assistant workflow covers asking the case a question.",
}

function filesUnder(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) filesUnder(p, out)
    else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) out.push(p)
  }
  return out
}

describe("the workflow catalogue (lx-workflowguide F)", () => {
  it("(1) every workflow in the list has a tutorial of 4 to 12 steps, each step complete", () => {
    const short = CATALOGUE.filter((w) => (TUTORIALS[w.id]?.length ?? 0) < 4 || (TUTORIALS[w.id]?.length ?? 0) > 12).map((w) => `${w.id}: ${TUTORIALS[w.id]?.length ?? 0} steps`)
    expect(short).toEqual([])
    const ids = CATALOGUE.map((w) => w.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(Object.keys(TUTORIALS).filter((id) => !ids.includes(id))).toEqual([])
    for (const w of CATALOGUE) {
      expect(w.useWhen.startsWith("Use this when"), w.id).toBe(true)
      expect(w.questions.length && w.kinds.length && w.areas.length, w.id).toBeTruthy()
      for (const q of w.questions) expect(QUESTIONS.some((g) => g.id === q), `${w.id} ${q}`).toBe(true)
      for (const k of w.kinds) expect(CASE_KINDS.some((g) => g.id === k), `${w.id} ${k}`).toBe(true)
      const steps = TUTORIALS[w.id] ?? []
      for (const s of steps) {
        for (const field of [s.title, s.body, s.expect, s.alt, s.shot]) expect(field?.trim(), `${w.id}: ${s.title}`).toBeTruthy()
        expect(s.open.to.startsWith("/"), `${w.id}: ${s.title} opens an address inside the case`).toBe(false)
      }
      // the list says which switches a workflow's steps wait behind
      const behind = [...new Set(steps.map((s) => s.switch).filter(Boolean))].sort()
      expect([...w.switches].sort(), `${w.id} switches`).toEqual(behind)
      // with every switch off, a person still has 4 steps, unless the whole workflow waits behind a switch
      const off = stepsShown(steps, { "corroborate-v2": false, phone_layers: false })
      if (off.length) expect(off.length, `${w.id} with switches off`).toBeGreaterThanOrEqual(4)
    }
  })

  it("(2) every step's pictures exist at both widths, are taken by the stills script, and every anchor it names exists", () => {
    const script = fs.readFileSync(path.join(front, "journeys/workflow-stills.mjs"), "utf8")
    const recipes = new Set([...script.matchAll(/^ {2}"([a-z0-9-]+)": async/gm)].map((m) => m[1]))
    const code = filesUnder(src).map((f) => fs.readFileSync(f, "utf8")).join("\n")
    const missing: string[] = []
    for (const [id, steps] of Object.entries(TUTORIALS)) {
      for (const s of steps) {
        if (!recipes.has(s.shot)) missing.push(`${id}: no recipe for ${s.shot}`)
        for (const w of [1440, 390]) if (!fs.existsSync(path.join(img, `${s.shot}-${w}.webp`))) missing.push(`${id}: ${s.shot}-${w}.webp`)
        for (const t of s.open.target ?? []) {
          const anchor = /\[data-guide="([^"]+)"\]/.exec(t)?.[1]
          if (anchor && !code.includes(`data-guide="${anchor}"`)) missing.push(`${id}: anchor ${anchor}`)
        }
      }
    }
    expect(missing).toEqual([])
  })

  it("(3) every feature in the guidance feature list appears in at least one workflow", () => {
    const ids = FEATURES.map((f) => f.id)
    const shown = new Set(CATALOGUE.flatMap((w) => w.features))
    expect(ids.filter((f) => !shown.has(f) && !EXCEPTIONS[f])).toEqual([])
    expect([...shown].filter((f) => !ids.includes(f))).toEqual([])
    expect(Object.keys(EXCEPTIONS).filter((f) => !ids.includes(f))).toEqual([])
    for (const f of Object.keys(EXCEPTIONS)) expect(shown.has(f), `${f} is listed as an exception and also shown`).toBe(false)
  })

  it("every workflow is linked from the guide of its first area, and every guide link names a workflow", () => {
    const docs = path.join(front, "public")
    const text = (id: keyof typeof GUIDES) => fs.readFileSync(path.join(docs, GUIDES[id].url.replace(/^\//, "")), "utf8")
    const unlinked = CATALOGUE.filter((w) => !text(AREA_GUIDE[w.areas[0]]).includes(`(#workflow=${w.id})`)).map((w) => w.id)
    expect(unlinked).toEqual([])
    const all = (Object.keys(GUIDES) as (keyof typeof GUIDES)[]).map(text).join("\n")
    const named = [...all.matchAll(/\(#workflow=([a-z0-9-]+)\)/g)].map((m) => m[1])
    expect(named.filter((id) => !CATALOGUE.some((w) => w.id === id))).toEqual([])
  })

  it("a step behind a switch that is off is hidden, and a workflow with no step left is not listed", () => {
    const on = workflowsShown({ "corroborate-v2": true, phone_layers: true })
    const off = workflowsShown({ "corroborate-v2": false, phone_layers: false })
    for (const w of off) expect(w.steps.every((s) => !s.switch), w.id).toBe(true)
    for (const w of on) expect(w.steps.length).toBe(TUTORIALS[w.id].length)
  })
})

const step = (n: number) => ({
  title: `Step title ${n}`,
  body: `Do thing ${n}.`,
  expect: `You see ${n}.`,
  shot: `shot-${n}`,
  alt: `Picture ${n}`,
  open: { to: "financial" },
})
const FAKE: Workflow = {
  id: "fake",
  title: "A fake workflow",
  useWhen: "Use this when testing.",
  questions: ["money"],
  kinds: ["any"],
  areas: ["financial"],
  features: [],
  switches: [],
  steps: [1, 2, 3, 4, 5].map(step),
}

/** The tutorial with its place held the way WorkflowGuide holds it. */
function Harness({ onList = vi.fn(), onOpen = vi.fn() }: { onList?: () => void; onOpen?: (n: number) => void }) {
  const [index, setIndex] = useState(0)
  return (
    <InDialog>
      <Tutorial workflow={FAKE} index={index} onStep={setIndex} onList={onList} onOpenScreen={onOpen} />
    </InDialog>
  )
}

function InDialog({ children }: { children: ReactNode }) {
  return (
    <Dialog open>
      <DialogContent>{children}</DialogContent>
    </Dialog>
  )
}

describe("(4) the tutorial's navigation", () => {
  const at = () => screen.getByText(/^Step \d+ of 5$/).textContent

  it("moves with Next and Previous, jumps from the side list, follows the arrow keys and goes back to the list", () => {
    const onList = vi.fn()
    const onOpen = vi.fn()
    render(<Harness onList={onList} onOpen={onOpen} />)
    expect(at()).toBe("Step 1 of 5")
    expect(screen.getByRole("img", { name: "Picture 1" }).getAttribute("loading")).toBe("lazy")
    fireEvent.click(screen.getByRole("button", { name: /^Next/ }))
    expect(at()).toBe("Step 2 of 5")
    expect(screen.getByRole("heading", { name: "Step title 2" })).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: /^Previous/ }))
    expect(at()).toBe("Step 1 of 5")
    // jump: the side list names every step
    const lists = screen.getAllByRole("navigation", { name: "Steps" })
    fireEvent.click(within(lists[1]).getByRole("button", { name: /Step title 4/ }))
    expect(at()).toBe("Step 4 of 5")
    // the phone-width strip jumps too
    fireEvent.click(within(lists[0]).getByRole("button", { name: "Step 2: Step title 2" }))
    expect(at()).toBe("Step 2 of 5")
    const panel = screen.getByTestId("workflow-tutorial")
    fireEvent.keyDown(panel, { key: "ArrowRight" })
    fireEvent.keyDown(panel, { key: "ArrowRight" })
    expect(at()).toBe("Step 4 of 5")
    fireEvent.keyDown(panel, { key: "ArrowLeft" })
    expect(at()).toBe("Step 3 of 5")
    fireEvent.click(screen.getByRole("button", { name: /Open this screen/ }))
    expect(onOpen).toHaveBeenCalledWith(2)
    // the last step offers the way back to the list
    fireEvent.keyDown(panel, { key: "ArrowRight" })
    fireEvent.keyDown(panel, { key: "ArrowRight" })
    fireEvent.keyDown(panel, { key: "ArrowRight" })
    expect(at()).toBe("Step 5 of 5")
    fireEvent.click(screen.getByRole("button", { name: /Done: all workflows/ }))
    fireEvent.click(screen.getByRole("button", { name: /All workflows/ }))
    expect(onList).toHaveBeenCalledTimes(2)
  })

  it("marks the current step for assistive technology", () => {
    render(<Harness />)
    const current = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "step")
    expect(current.length).toBe(2)
  })
})

describe("the step bar after Open this screen", () => {
  it("says what to open first for a control inside something opened, and never calls that control missing", () => {
    vi.useFakeTimers()
    try {
      const inside = { ...step(2), open: { to: "workspace", target: ['[data-guide="nowhere-yet"]'], then: "Click a theory to open it." } }
      const { unmount } = render(<StepReturn workflow={FAKE} index={1} step={inside} onBack={vi.fn()} onClose={vi.fn()} />)
      expect(screen.getByText("Click a theory to open it.")).toBeTruthy()
      act(() => void vi.advanceTimersByTime(21_000))
      expect(screen.queryByText(/not on this screen/)).toBeNull()
      unmount()
      // the way to the control (a later target) is ringed and the line stays until the control itself is ringed
      const way = document.createElement("button")
      way.setAttribute("data-guide", "the-way")
      way.getBoundingClientRect = () => ({ x: 0, y: 0, top: 0, left: 0, right: 40, bottom: 20, width: 40, height: 20, toJSON: () => ({}) })
      document.body.appendChild(way)
      const both = { ...step(2), open: { to: "workspace", target: ['[data-guide="the-control"]', '[data-guide="the-way"]'], then: "Open Details on a payment." } }
      const second = render(<StepReturn workflow={FAKE} index={1} step={both} onBack={vi.fn()} onClose={vi.fn()} />)
      expect(screen.getByTestId("workflow-ring")).toBeTruthy()
      expect(screen.getByText("Open Details on a payment.")).toBeTruthy()
      const control = way.cloneNode() as HTMLButtonElement
      control.setAttribute("data-guide", "the-control")
      control.getBoundingClientRect = way.getBoundingClientRect
      document.body.appendChild(control)
      act(() => void vi.advanceTimersByTime(600))
      expect(screen.queryByText("Open Details on a payment.")).toBeNull()
      second.unmount()
      way.remove()
      control.remove()
      // a control with nothing to open first is said to be missing once the screen has had 20 seconds to load
      render(<StepReturn workflow={FAKE} index={1} step={{ ...step(2), open: { to: "workspace", target: ['[data-guide="nowhere-yet"]'] } }} onBack={vi.fn()} onClose={vi.fn()} />)
      expect(screen.queryByText(/not on this screen/)).toBeNull()
      act(() => void vi.advanceTimersByTime(21_000))
      expect(screen.getByText(/not on this screen/)).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })
})

describe("the workflow list", () => {
  it("finds a workflow by its words and groups by question or by kind of case", () => {
    const onPick = vi.fn()
    const other: Workflow = { ...FAKE, id: "other", title: "Phones on the map", useWhen: "Use this when a phone matters.", questions: ["there"], kinds: ["defence"] }
    render(
      <InDialog>
        <WorkflowList workflows={[FAKE, other]} onPick={onPick} />
      </InDialog>
    )
    expect(screen.getByText("Where did the money go?")).toBeTruthy()
    fireEvent.change(screen.getByRole("textbox", { name: "Find a workflow" }), { target: { value: "map" } })
    expect(screen.queryByText("A fake workflow")).toBeNull()
    expect(screen.getByText("1 of 2 workflows")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "By kind of case" }))
    expect(screen.getByText("Defence and review")).toBeTruthy()
    fireEvent.click(screen.getByText("Phones on the map"))
    expect(onPick).toHaveBeenCalledWith("other")
  })
})
