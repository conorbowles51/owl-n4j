import { expect, it } from "vitest"
import { requestWords } from "@/lib/request-progress"

// The waiting standard (spec 07 section 4.7): a page or panel that waits for its data shows the shared loading
// panel (LoadProgress: the step in words, true counts, time left), never a bare spinner. Spinners inside a
// button next to its own words are not page waits. The phone screens (features/cellebrite), and the screens the
// phone units add phone data to and replace the spinner on (spec 07 finding 1: the route fallback in unit 03-1,
// Map and Table), are those units' own.
const sources = import.meta.glob(["../**/*.tsx", "!../**/*.test.tsx", "!../features/cellebrite/**", "!../app/routes.tsx",
  "!../features/map/components/MapPage.tsx", "!../features/table/components/TablePage.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

it("no page or panel waits behind a bare spinner", () => {
  const bare = /<div className="flex (?:h-full|h-screen|min-h-96|flex-1|justify-center py-8)[^"]*items-center justify-center[^"]*">\s*<LoadingSpinner|<div className="flex justify-center py-8">\s*<LoadingSpinner/g
  const found = Object.entries(sources).flatMap(([path, text]) => (text.match(bare) ? [path] : []))
  expect(Object.keys(sources).length).toBeGreaterThan(100)
  expect(found).toEqual([])
})

it("names in words what the admin, workspace and triage pages wait for", () => {
  expect(requestWords("/api/users")).toBe("users")
  expect(requestWords("/api/admin/tasks")).toBe("background tasks")
  expect(requestWords("/api/admin/ai-costs/summary?x=1")).toBe("AI costs")
  expect(requestWords("/api/workspace/c1/context")).toBe("the workspace")
  expect(requestWords("/api/triage/cases")).toBe("triage cases")
})
