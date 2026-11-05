import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AddNodeDialog } from "./AddNodeDialog"
import { graphAPI } from "../api"

vi.mock("../api", () => ({ graphAPI: { createNode: vi.fn() } }))

const createNode = vi.mocked(graphAPI.createNode)

function open() {
  const onOpenChange = vi.fn()
  const onCreated = vi.fn()
  render(<AddNodeDialog open onOpenChange={onOpenChange} caseId="case-a" onCreated={onCreated} />)
  return { onOpenChange, onCreated }
}

describe("AddNodeDialog", () => {
  beforeEach(() => createNode.mockReset())

  it("stays open and says why when the server refuses", async () => {
    createNode.mockResolvedValue({ success: false, node_key: "k", error: '"K" is already in this case; nothing was changed.' })
    const { onOpenChange, onCreated } = open()
    await userEvent.type(screen.getByPlaceholderText("Entity name"), "K")
    await userEvent.click(screen.getByRole("button", { name: "Create" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("already in this case")
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
  })

  it("hands back the key the server made", async () => {
    createNode.mockResolvedValue({ success: true, node_key: "k-1234" })
    const { onOpenChange, onCreated } = open()
    await userEvent.type(screen.getByPlaceholderText("Entity name"), "K")
    await userEvent.click(screen.getByRole("button", { name: "Create" }))
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("k-1234"))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
