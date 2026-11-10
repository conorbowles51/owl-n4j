import {
  act,
  cleanup,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  BrowserRouter,
  Link,
  MemoryRouter,
  Route,
  Routes,
} from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { CaseContextSection } from "./CaseContextSection"
import { TasksSection } from "./TasksSection"
import { CaseworkEditor } from "./CaseworkEditor"
import type { CaseContext, CaseWorkResponse } from "../api"
import type { CaseworkEntry } from "../casework-api"
import "@/styles/globals.css"
import { initializeUnsavedHistoryGuard } from "@/hooks/use-unsaved-history-guard"

const originalBrowserUrl = window.location.href
const originalBrowserState = window.history.state
initializeUnsavedHistoryGuard()

let context: CaseContext
let work: CaseWorkResponse
let failSave: boolean
let failList: boolean
let linkedNoteLinks: CaseworkEntry["links"]
let parentChoices: CaseWorkResponse["tasks"]
let failChoices: boolean
let holdSave: Promise<void> | null
let writes: Array<{ url: string; body: Record<string, unknown> }>
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  })
beforeEach(async () => {
  await page.viewport(1280, 900)
  failSave = false
  failList = false
  linkedNoteLinks = []
  failChoices = false
  holdSave = null
  writes = []
  context = {
    case_id: "case-1",
    case_summary: "Review the witness accounts",
    active_template_key: "criminal_defense",
    custom_values: {
      client_profile: "Existing client",
      charges: "Charge A",
      allegations: "Allegation B",
      denials: "Client's previously recorded account",
      legal_exposure: "Earlier assessment",
      court_info: "Dublin Circuit Court",
    },
    mandate_complete: true,
    active_mandate: {
      id: "objective-1",
      case_id: "case-1",
      version_number: 1,
      objective: "Establish what happened",
      key_questions: ["Who was present?"],
      perspective: "Test competing explanations",
      constraints: "Cite source material",
    },
    templates: [
      {
        key: "generic",
        name: "General investigation",
        is_builtin: true,
        fields: [],
      },
      {
        key: "criminal_defense",
        name: "Criminal defence",
        is_builtin: true,
        fields: [
          ["client_profile", "Client profile"],
          ["charges", "Charges"],
          ["allegations", "Allegations"],
          ["defense_strategy", "Defence strategy"],
          ["denials", "Denials"],
          ["legal_exposure", "Legal exposure"],
          ["court_info", "Court information"],
        ].map(([key, label], position) => ({
          key,
          label,
          position,
          type: "long_text",
          choices: [],
          required: false,
        })),
      },
    ],
  }
  context.template_values = { criminal_defense: { ...context.custom_values } }
  const today = new Date()
  const localDay = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`
  work = {
    tasks: [
      {
        id: "task-1",
        title: "Interview witness",
        status: "todo",
        priority: "standard",
        links: [],
        due_at: null,
        subtask_progress: { done: 0, total: 0 },
      },
    ],
    task_total: 1,
    deadlines: [
      {
        id: "deadline-1",
        case_id: "case-1",
        name: "Court filing",
        due_date: localDay,
      },
    ],
    deadline_total: 1,
    bounded: true,
    limit: 100,
  }
  parentChoices = [...work.tasks]
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? "GET"
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    if (method !== "GET") writes.push({ url, body })
    if (method !== "GET" && holdSave) await holdSave
    if (method !== "GET" && failSave)
      return json({ detail: "Save failed; please retry" }, 503)
    if (url.includes("/context/mandates")) {
      if (method === "POST") {
        context.active_mandate = {
          ...body,
          id: "objective-2",
          case_id: "case-1",
          version_number: 2,
        }
        return json(context.active_mandate)
      }
      return json({ versions: [context.active_mandate] })
    }
    if (url.includes("/context")) {
      if (method === "PUT") {
        const templates = { ...context.template_values }
        for (const [key, fields] of Object.entries(body.template_values ?? {}))
          templates[key] = {
            ...templates[key],
            ...(fields as Record<string, unknown>),
          }
        templates[body.active_template_key] = {
          ...templates[body.active_template_key],
          ...body.custom_values,
        }
        context = {
          ...context,
          ...body,
          template_values: templates,
          custom_values: templates[body.active_template_key],
        }
      }
      return json(context)
    }
    if (url.includes("/dossiers")) return json({ dossiers: [], total: 0 })
    if (url.includes("/members")) return json({ members: [], total: 0 })
    if (url.includes("/attachment-options"))
      return json({ options: [], total: 0 })
    if (url.includes("/significance"))
      return json({
        id: "finding-1",
        entry_type: "finding",
        version: 3,
        significance: body.significance,
      })
    if (url.includes("/entries/linked-note") && method === "GET")
      return json({
        id: "linked-note",
        case_id: "case-1",
        entry_type: "note",
        title: "Witness account",
        body: "The witness described the arrival time.",
        version: 1,
        lifecycle_state: "active",
        review_state: "accepted",
        tags: [],
        links: linkedNoteLinks,
        migration_metadata: {},
        needs_migration_review: false,
        revisions: [],
        events: [],
      })
    if (url.includes("/entries"))
      return json({
        ...body,
        id: "finding-1",
        entry_type: "finding",
        version: 2,
      })
    if (/\/work(?:\?|$)/.test(url)) {
      if (failList) return json({ detail: "Temporarily unavailable" }, 503)
      if (url.includes("offset=100"))
        return json({
          ...work,
          tasks: [
            { ...work.tasks[0], id: "task-page-2", title: "Second-page task" },
          ],
          deadlines: [],
        })
      return json(work)
    }
    if (url.includes("/tasks/hidden-task"))
      return json({
        ...work.tasks[0],
        id: "hidden-task",
        title: "Linked task beyond first page",
      })
    if (url.includes("parent_candidates=true")) {
      if (failChoices) return json({ detail: "Options unavailable" }, 503)
      const params = new URL(url, "http://localhost").searchParams
      const search = (params.get("search") ?? "").toLowerCase()
      const offset = Number(params.get("offset") ?? 0)
      const options = parentChoices.filter((task) =>
        task.title.toLowerCase().includes(search)
      )
      return json({
        tasks: options.slice(offset, offset + 50),
        total: options.length,
        limit: 50,
        offset,
      })
    }
    if (url.includes("/tasks")) {
      if (method === "POST") {
        const task = {
          ...body,
          id: "task-new",
          subtask_progress: { done: 0, total: 0 },
        }
        work.tasks.push(task)
        work.task_total++
        return json(task)
      }
      if (method === "PATCH") {
        work.tasks[0] = { ...work.tasks[0], ...body }
        return json(work.tasks[0])
      }
      return json({ detail: "Not found" }, 404)
    }
    if (url.includes("/deadlines")) {
      if (method === "GET" && failChoices)
        return json({ detail: "Options unavailable" }, 503)
      if (method === "POST") {
        const deadline = { ...body, id: "deadline-new", case_id: "case-1" }
        work.deadlines.push(deadline)
        work.deadline_total++
        return json(deadline)
      }
      if (method === "PATCH") {
        work.deadlines[0] = {
          ...work.deadlines[0],
          ...body,
          ...("completed" in body
            ? { completed_at: body.completed ? new Date().toISOString() : null }
            : {}),
        }
        return json(work.deadlines[0])
      }
      return json({ deadlines: work.deadlines, total: work.deadline_total })
    }
    return json({ detail: `Unexpected request ${url}` }, 404)
  })
})
afterEach(async () => {
  cleanup()
  vi.restoreAllMocks()
  window.history.replaceState(originalBrowserState, "", originalBrowserUrl)
  await page.viewport(1280, 900)
})
function mount(child: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>{child}</QueryClientProvider>
    </MemoryRouter>
  )
}

function mountHistoryJourney(child: React.ReactNode) {
  window.history.replaceState({ idx: 0 }, "", "/workspace-history-start")
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <BrowserRouter>
      <QueryClientProvider client={client}>
        <Routes>
          <Route
            path="/workspace-history-start"
            element={
              <>
                <h1>Before workspace</h1>
                <Link to="/workspace-history-edit">Open working screen</Link>
              </>
            }
          />
          <Route path="/workspace-history-edit" element={child} />
        </Routes>
      </QueryClientProvider>
    </BrowserRouter>
  )
}

describe("Workspace setup and deadlines journeys", () => {
  for (const surface of ["setup", "task", "casework"] as const) {
    it(`keeps the actual ${surface} draft when browser Back is cancelled`, async () => {
      const user = userEvent.setup()
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
      mountHistoryJourney(
        surface === "setup" ? (
          <CaseContextSection caseId="case-1" canEdit />
        ) : surface === "task" ? (
          <TasksSection caseId="case-1" canEdit />
        ) : (
          <CaseworkEditor caseId="case-1" initialType="note" canEdit />
        )
      )
      await user.click(
        screen.getByRole("link", { name: "Open working screen" })
      )
      if (surface === "setup")
        await user.click(
          await screen.findByRole("button", { name: "Edit summary" })
        )
      if (surface === "task")
        await user.click(
          await screen.findByRole("button", { name: "Open Interview witness" })
        )
      const label =
        surface === "setup"
          ? "Case summary"
          : surface === "task"
            ? "Task description"
            : "Casework"
      const field = await screen.findByLabelText(label)
      await user.clear(field)
      await user.type(field, `Unsaved ${surface} draft`)
      const index = window.history.state.idx
      act(() => window.history.back())
      await waitFor(() => expect(confirm).toHaveBeenCalledOnce(), {
        timeout: 3000,
      })
      await waitFor(() => expect(window.history.state.idx).toBe(index), {
        timeout: 3000,
      })
      expect(screen.getByLabelText(label)).toHaveValue(
        `Unsaved ${surface} draft`
      )
      confirm.mockReturnValue(true)
      act(() => window.history.back())
      expect(
        await screen.findByRole(
          "heading",
          { name: "Before workspace" },
          { timeout: 3000 }
        )
      ).toBeVisible()
      expect(writes).toHaveLength(0)
    })
  }
  it("preserves existing and newly entered template information through switching, saving and reopening", async () => {
    const user = userEvent.setup()
    mount(<CaseContextSection caseId="case-1" canEdit />)
    await user.click(
      await screen.findByRole("button", { name: "Edit summary" })
    )
    expect(
      screen.queryByRole("textbox", { name: "Denials" })
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText("Court information")).toHaveValue(
      "Dublin Circuit Court"
    )
    if (import.meta.env.VITE_WORKSPACE_CAPTURE_DIR)
      await page.screenshot({
        path: `${import.meta.env.VITE_WORKSPACE_CAPTURE_DIR}/workspace-setup.png`,
      })
    await user.clear(screen.getByLabelText("Charges"))
    await user.type(screen.getByLabelText("Charges"), "Revised charge")
    await user.selectOptions(
      screen.getByLabelText("Specialised template"),
      "generic"
    )
    await user.selectOptions(
      screen.getByLabelText("Specialised template"),
      "criminal_defense"
    )
    expect(screen.getByLabelText("Charges")).toHaveValue("Revised charge")
    await user.click(screen.getByRole("button", { name: "Save summary" }))
    await user.click(
      await screen.findByRole("button", { name: "Edit summary" })
    )
    expect(screen.getByLabelText("Charges")).toHaveValue("Revised charge")
    expect(context.custom_values.denials).toBe(
      "Client's previously recorded account"
    )
    expect(context.custom_values.legal_exposure).toBe("Earlier assessment")
  })
  it("saves a simple objective, keeps advanced instructions and recovers a failed save", async () => {
    const user = userEvent.setup()
    mount(<CaseContextSection caseId="case-1" canEdit />)
    await user.click(
      await screen.findByRole("button", { name: "Edit objective" })
    )
    expect(screen.getByLabelText("Perspective / posture")).not.toBeVisible()
    await user.clear(screen.getByLabelText("Objective"))
    await user.type(
      screen.getByLabelText("Objective"),
      "Test the revised account"
    )
    failSave = true
    await user.click(screen.getByRole("button", { name: "Save objective" }))
    await waitFor(() =>
      expect(writes.some((w) => w.url.includes("mandates"))).toBe(true)
    )
    expect(screen.getByLabelText("Objective")).toHaveValue(
      "Test the revised account"
    )
    failSave = false
    await user.click(screen.getByRole("button", { name: "Save objective" }))
    await screen.findByRole("button", { name: "Edit objective" })
    expect(context.active_mandate?.perspective).toBe(
      "Test competing explanations"
    )
    expect(context.active_mandate?.key_questions).toEqual(["Who was present?"])
    await user.click(screen.getByRole("button", { name: "Edit objective" }))
    expect(screen.getByLabelText("Objective")).toHaveValue(
      "Test the revised account"
    )
  })
  it("warns on cancel and keeps a draft when discarding is declined", async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    mount(<CaseContextSection caseId="case-1" canEdit />)
    await user.click(
      await screen.findByRole("button", { name: "Edit summary" })
    )
    await user.type(screen.getByLabelText("Case summary"), " revised")
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(confirm).toHaveBeenCalled()
    expect(screen.getByLabelText("Case summary")).toHaveValue(
      "Review the witness accounts revised"
    )
  })
  it("shows undated tasks and today's deadline together and creates both types from Add new", async () => {
    const user = userEvent.setup()
    mount(<TasksSection caseId="case-1" canEdit />)
    await screen.findByRole("button", { name: "Open Interview witness" })
    expect(
      screen.getByRole("button", { name: "Open Court filing" })
    ).toHaveTextContent("Today")
    expect(screen.getByRole("heading", { name: "No due date" })).toBeVisible()
    await user.click(screen.getByRole("button", { name: "Add new" }))
    await user.click(screen.getByRole("button", { name: "Task" }))
    await user.type(
      screen.getByLabelText("Task title"),
      "Prepare witness questions"
    )
    await user.click(screen.getByRole("button", { name: "Create task" }))
    expect(
      await screen.findByRole("button", {
        name: "Open Prepare witness questions",
      })
    ).toBeVisible()
    await user.click(screen.getByRole("button", { name: "Add new" }))
    await user.click(screen.getByRole("button", { name: "Deadline" }))
    await user.type(screen.getByLabelText("Deadline name"), "Response due")
    await user.type(screen.getByLabelText("Deadline due date"), "2026-11-01")
    await user.click(screen.getByRole("button", { name: "Create deadline" }))
    expect(
      await screen.findByRole("button", { name: "Open Response due" })
    ).toBeVisible()
    await user.selectOptions(screen.getByLabelText("Type"), "deadlines")
    expect(
      screen.queryByRole("button", { name: "Open Prepare witness questions" })
    ).not.toBeInTheDocument()
  })
  it("edits the exact linked item beyond the list page and retains changes after failure", async () => {
    const user = userEvent.setup()
    mount(<TasksSection caseId="case-1" canEdit initialItemId="hidden-task" />)
    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByLabelText("Task title")).toHaveValue(
      "Linked task beyond first page"
    )
    await user.type(
      screen.getByLabelText("Task description"),
      "My edited context"
    )
    failSave = true
    await user.click(screen.getByRole("button", { name: "Save changes" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Save failed")
    expect(screen.getByLabelText("Task description")).toHaveValue(
      "My edited context"
    )
    failSave = false
    await user.click(screen.getByRole("button", { name: "Save changes" }))
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
    expect(writes.at(-1)?.url).toContain("hidden-task")
  })
  it("completes, reopens and retries deadlines without changing linked tasks", async () => {
    const user = userEvent.setup()
    mount(<TasksSection caseId="case-1" canEdit />)
    await user.click(
      await screen.findByRole("checkbox", {
        name: "Mark Court filing complete",
      })
    )
    expect(
      await screen.findByRole("checkbox", { name: "Reopen Court filing" })
    ).toBeChecked()
    expect(screen.getByRole("region", { name: "Completed" })).toHaveTextContent(
      "Court filing"
    )
    expect(
      screen.getByRole("checkbox", { name: "Mark Interview witness complete" })
    ).not.toBeChecked()
    await user.click(screen.getByRole("button", { name: "Open Court filing" }))
    expect(screen.getByLabelText("Deadline completed")).toBeChecked()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    failSave = true
    await user.click(
      screen.getByRole("checkbox", { name: "Reopen Court filing" })
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "was not changed"
    )
    expect(
      screen.getByRole("checkbox", { name: "Reopen Court filing" })
    ).toBeChecked()
    failSave = false
    await user.click(screen.getByRole("button", { name: "Try again" }))
    expect(
      await screen.findByRole("checkbox", {
        name: "Mark Court filing complete",
      })
    ).not.toBeChecked()
    expect(screen.getByRole("region", { name: "Today" })).toHaveTextContent(
      "Court filing"
    )
    expect(
      writes
        .filter((write) => write.url.includes("/deadlines/"))
        .map((write) => write.body.completed)
    ).toEqual([true, false, false])
  })
  it("opens the task's linked casework and returns to the unchanged task draft", async () => {
    const user = userEvent.setup()
    work.tasks[0].links = [
      {
        target_type: "entry",
        target_id: "linked-note",
        label: "Witness account",
      },
    ]
    mount(<TasksSection caseId="case-1" canEdit />)
    await user.click(
      await screen.findByRole("button", { name: "Open Interview witness" })
    )
    await user.type(
      screen.getByLabelText("Task description"),
      "Follow up on the arrival time"
    )
    await user.click(
      screen.getByRole("button", { name: "Open Witness account (casework)" })
    )
    const linked = await screen.findByRole("dialog", {
      name: "Witness account",
    })
    expect(
      within(linked).getByText("The witness described the arrival time.")
    ).toBeVisible()
    await user.click(within(linked).getByRole("button", { name: "Close" }))
    expect(screen.getByLabelText("Task description")).toHaveValue(
      "Follow up on the arrival time"
    )
    await user.click(screen.getByRole("button", { name: "Save changes" }))
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
    expect(work.tasks[0].links[0].target_id).toBe("linked-note")
  })
  it("asks before a linked source navigates away from an unsaved task", async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    work.tasks[0].links = [
      {
        target_type: "entry",
        target_id: "linked-note",
        label: "Witness account",
      },
    ]
    linkedNoteLinks = [
      {
        id: "graph-link",
        entry_id: "linked-note",
        case_id: "case-1",
        target_type: "graph_entity",
        target_id: "person-1",
        target_label: "Morgan Example",
        relationship: "context",
        source_anchor: {},
        metadata: {},
      },
    ]
    mount(
      <Routes>
        <Route path="/" element={<TasksSection caseId="case-1" canEdit />} />
        <Route
          path="/cases/case-1/graph"
          element={<h1>Graph destination</h1>}
        />
      </Routes>
    )
    await user.click(
      await screen.findByRole("button", { name: "Open Interview witness" })
    )
    await user.type(
      screen.getByLabelText("Task description"),
      "Draft to preserve"
    )
    await user.click(
      screen.getByRole("button", { name: "Open Witness account (casework)" })
    )
    const source = await screen.findByRole("dialog", {
      name: "Witness account",
    })
    await user.click(
      within(source).getByRole("button", { name: /Morgan Example/ })
    )
    expect(confirm).toHaveBeenCalledWith("Discard your unsaved task changes?")
    expect(
      screen.queryByRole("heading", { name: "Graph destination" })
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText("Task description")).toHaveValue(
      "Draft to preserve"
    )
    confirm.mockReturnValue(true)
    await user.click(
      within(source).getByRole("button", { name: /Morgan Example/ })
    )
    expect(
      await screen.findByRole("heading", { name: "Graph destination" })
    ).toBeVisible()
    expect(writes.filter((write) => write.url.includes("/tasks"))).toHaveLength(
      0
    )
  })
  it("links case-wide deadlines and searches later parent-task pages from a filtered list", async () => {
    const user = userEvent.setup()
    parentChoices = Array.from({ length: 55 }, (_, i) => ({
      ...work.tasks[0],
      id: `parent-${i}`,
      title: `Parent task ${i}`,
    }))
    mount(<TasksSection caseId="case-1" canEdit />)
    await screen.findByRole("button", { name: "Open Interview witness" })
    await user.selectOptions(screen.getByLabelText("Status"), "in_progress")
    await user.click(screen.getByRole("button", { name: "Add new" }))
    await user.click(screen.getByRole("button", { name: "Task" }))
    await user.type(screen.getByLabelText("Task title"), "Follow the source")
    await screen.findByRole("option", { name: /Court filing/ })
    await user.selectOptions(
      screen.getByLabelText("Linked deadline"),
      "deadline-1"
    )
    await user.click(
      await screen.findByRole("button", { name: "Next parent tasks" })
    )
    await screen.findByRole("option", { name: "Parent task 51" })
    await user.selectOptions(screen.getByLabelText("Parent task"), "parent-51")
    await user.type(
      screen.getByLabelText("Search parent tasks"),
      "Parent task 54"
    )
    await screen.findByRole("option", { name: "Parent task 54" })
    expect(screen.getByLabelText("Parent task")).toHaveValue("parent-51")
    await user.click(screen.getByRole("button", { name: "Create task" }))
    await waitFor(() =>
      expect(
        writes.some(
          (write) =>
            write.body.parent_task_id === "parent-51" &&
            write.body.deadline_id === "deadline-1"
        )
      ).toBe(true)
    )
  })
  it("keeps a task draft while failed linking choices are retried", async () => {
    const user = userEvent.setup()
    failChoices = true
    mount(<TasksSection caseId="case-1" canEdit />)
    await screen.findByRole("button", { name: "Open Interview witness" })
    await user.click(screen.getByRole("button", { name: "Add new" }))
    await user.click(screen.getByRole("button", { name: "Task" }))
    await user.type(screen.getByLabelText("Task title"), "Keep this draft")
    await screen.findByRole("button", { name: "Retry deadline choices" })
    failChoices = false
    await user.click(
      screen.getByRole("button", { name: "Retry deadline choices" })
    )
    await user.click(screen.getByRole("button", { name: "Retry parent tasks" }))
    await screen.findByRole("option", { name: /Court filing/ })
    await screen.findByRole("option", { name: "Interview witness" })
    expect(screen.getByLabelText("Task title")).toHaveValue("Keep this draft")
  })
  it("asks once on dirty Escape and cannot dismiss a task while saving", async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    mount(<TasksSection caseId="case-1" canEdit />)
    await screen.findByRole("button", { name: "Open Interview witness" })
    await user.click(screen.getByRole("button", { name: "Add new" }))
    await user.click(screen.getByRole("button", { name: "Task" }))
    await user.type(screen.getByLabelText("Task title"), "Save this task")
    await user.keyboard("{Escape}")
    expect(confirm).toHaveBeenCalledOnce()
    expect(screen.getByLabelText("Task title")).toHaveValue("Save this task")
    confirm.mockClear()
    let releaseSave: () => void = () => {}
    holdSave = new Promise((resolve) => { releaseSave = resolve })
    try {
      await user.click(screen.getByRole("button", { name: "Create task" }))
      expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled()
      await user.keyboard("{Escape}")
      expect(screen.getByRole("dialog")).toBeVisible()
      expect(confirm).not.toHaveBeenCalled()
    } finally { releaseSave() }
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })
  it("loads beyond the first page and retries a failed list request", async () => {
    const user = userEvent.setup()
    failList = true
    mount(<TasksSection caseId="case-1" canEdit />)
    await screen.findByRole("alert")
    failList = false
    work.task_total = 101
    await user.click(screen.getByRole("button", { name: "Try again" }))
    await user.click(
      await screen.findByRole("button", {
        name: "Load more tasks and deadlines",
      })
    )
    expect(
      await screen.findByRole("button", { name: "Open Second-page task" })
    ).toBeVisible()
  })
  it("keeps the combined list usable and read only on mobile", async () => {
    await page.viewport(390, 844)
    const user = userEvent.setup()
    mount(<TasksSection caseId="case-1" canEdit={false} />)
    await user.click(
      await screen.findByRole("button", { name: "Open Court filing" })
    )
    expect(screen.getByRole("heading", { name: "View deadline" })).toBeVisible()
    expect(screen.getByLabelText("Deadline name")).toBeDisabled()
    await user.click(screen.getAllByRole("button", { name: "Close" }).at(-1)!)
    expect(
      screen.queryByRole("button", { name: "Add new" })
    ).not.toBeInTheDocument()
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
    if (import.meta.env.VITE_WORKSPACE_CAPTURE_DIR)
      await page.screenshot({
        path: `${import.meta.env.VITE_WORKSPACE_CAPTURE_DIR}/workspace-deadlines-mobile.png`,
      })
  })
  it("clears an existing finding assessment explicitly rather than defaulting it to Medium", async () => {
    const user = userEvent.setup()
    const entry: CaseworkEntry = {
      id: "finding-1",
      case_id: "case-1",
      entry_type: "finding",
      title: "Recorded finding",
      body: "The account changed.",
      tags: [],
      significance: "high",
      confidence: null,
      lifecycle_state: "draft",
      version: 1,
      review_state: "accepted",
      links: [],
      migration_metadata: {},
      needs_migration_review: false,
    }
    mount(<CaseworkEditor caseId="case-1" entry={entry} canEdit />)
    await user.click(screen.getByRole("combobox", { name: "Significance" }))
    await user.click(
      screen.getByRole("option", { name: "Unrated — no assessment yet" })
    )
    await user.click(screen.getByRole("button", { name: "Save changes" }))
    await waitFor(() =>
      expect(
        writes.some(
          (w) => w.url.includes("/significance") && w.body.significance === null
        )
      ).toBe(true)
    )
  })
})
