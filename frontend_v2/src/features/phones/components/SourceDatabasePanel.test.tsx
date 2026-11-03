import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 section 17.2 / 03 3.6 point 6: the record's source line in each state, and the row read from the file. */
const api = vi.hoisted(() => ({ getSourceDatabase: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { SourceDatabasePanel } from "./SourceDatabasePanel"
import type { RecordDetail } from "../schemas"

const NONE = "The production does not include the app database this record was read from."
const base = { record_uid: "r-1" } as unknown as RecordDetail
const withRow = (source_row: RecordDetail["source_row"]) => ({ ...base, source_row }) as RecordDetail

function show(detail: RecordDetail) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SourceDatabasePanel caseId="case-1" detail={detail} />
    </QueryClientProvider>,
  )
}

describe("Source database panel wording", () => {
  it("says the production holds no app database when nothing links", () => {
    show(withRow({ available: false, reason: NONE, files: [] }))
    expect(screen.getByText(NONE)).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("names the file that is absent or mismatched and offers nothing to open", () => {
    show(withRow({
      available: false, reason: "The 2 app databases this record was read from: 1 not in the production; 1 does not match its MD5 in the report.",
      files: [
        { file_uid: "f1", original_path: "/data/synthetic/a.db", state: "absent", state_words: "The report lists this file, but it is not in the production." },
        { file_uid: "f2", original_path: "/data/synthetic/b.db", state: "md5_mismatch", state_words: "The file in the production does not match the MD5 in the report." },
      ],
    }))
    expect(screen.getByText(/1 not in the production; 1 does not match its MD5/)).toBeInTheDocument()
    expect(screen.getByText("/data/synthetic/a.db: The report lists this file, but it is not in the production.")).toBeInTheDocument()
    expect(screen.getByText("/data/synthetic/b.db: The file in the production does not match the MD5 in the report.")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("says the report does not name the row when it names only the file", () => {
    show(withRow({ available: true, row_named: false, reason: "The report does not say which row this record came from.", source_index: 1 }))
    expect(screen.getByText("The report does not say which row this record came from.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open source database" })).toBeInTheDocument()
  })

  it("opens the named row as read from the file, values raw, never as the report's record", async () => {
    api.getSourceDatabase.mockResolvedValue({
      record_uid: "r-1", refused: null, read_by: "x",
      source: { mechanism: "extra_info", table_name: "messages", offset: "12", state: "verified", file: { original_path: "/data/synthetic/app.db", sha256: "ab" } },
      view: {
        open_mode: "read-only, immutable",
        tables: [{ name: "messages", type: "table", schema: "CREATE TABLE messages (...)", row_count: 1200, count_note: null }],
        named_row: { found: true, rowid: 12, columns: ["(rowid)", "id", "body", "data"], values: [12, 12, "synthetic", { blob_bytes: 100, hex_preview: "0001", preview_complete: false }] },
        copy: { sha256: "c0ffee", size: 4096, siblings: [{ suffix: "-wal", sha256: "d1", size: 4152 }] },
        opened_by: { module: "app.phone.source_db", version: "1", sqlite: "3.46.1" },
      },
    })
    show(withRow({ available: true, row_named: true, reason: null, source_index: 2, table_name: "messages", offset: "12" }))
    fireEvent.click(screen.getByRole("button", { name: "Open source row" }))
    expect(await screen.findByText(/Read from the app database \/data\/synthetic\/app\.db by Loupe's read-only viewer; this is the file's content, not the report's record\./)).toBeInTheDocument()
    expect(api.getSourceDatabase).toHaveBeenCalledWith("case-1", "r-1", 2, undefined, 1)
    expect(screen.getByText("The report says this record came from table messages, position 12.")).toBeInTheDocument()
    const row = screen.getByRole("table", { name: "Source row" })
    expect(row).toHaveTextContent("synthetic")
    expect(row).toHaveTextContent("100 bytes: 0001 …")
    expect(screen.getByText(/-wal \(4,152 bytes\)/)).toBeInTheDocument()
    expect(screen.getByText("1,200 rows", { exact: false })).toBeInTheDocument()
  })

  it("shows the reason when the server refuses to open the file", async () => {
    api.getSourceDatabase.mockResolvedValue({
      record_uid: "r-1", refused: "This file is not an SQLite database.", read_by: "x",
      source: { mechanism: "jump_target", table_name: null, offset: null, state: "verified", file: { original_path: "/data/x", sha256: null } },
      view: null,
    })
    show(withRow({ available: true, row_named: false, reason: "The report does not say which row this record came from.", source_index: 0 }))
    fireEvent.click(screen.getByRole("button", { name: "Open source database" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("This file is not an SQLite database.")
  })
})
