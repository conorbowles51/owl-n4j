import { Suspense } from "react"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, expect, it } from "vitest"
import { resetPageChunks } from "@/lib/page-chunks"
import { timedLazy } from "@/lib/timed-lazy"
import { PageLoading } from "./page-loading"

// A route page (routes.tsx loads every page through timedLazy) whose code never arrives: what the person sees is
// the fallback alone.
const NeverArrives = timedLazy(() => new Promise<{ default: () => null }>(() => {}))
afterEach(() => resetPageChunks())

it("a lazy route page shows the loading panel, in words, before its code arrives", async () => {
  render(
    <MemoryRouter initialEntries={["/cases/case-1/evidence"]}>
      <Routes>
        <Route
          path="/cases/:id/evidence"
          element={
            <Suspense fallback={<PageLoading />}>
              <NeverArrives />
            </Suspense>
          }
        />
      </Routes>
    </MemoryRouter>
  )
  expect(await screen.findByTestId("load-progress", undefined, { timeout: 5_000 })).toBeInTheDocument()
  expect(screen.getByRole("status")).toBeInTheDocument()
})
