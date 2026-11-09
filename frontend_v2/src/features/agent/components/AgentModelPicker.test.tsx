import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"

import { AgentModelPicker } from "./AgentModelPicker"
import { modelParams } from "../agent-model-choice"
import type { AgentModelChoice } from "../types"

const choices: AgentModelChoice[] = [
  { key: "deepseek-v4-pro:off", provider: "deepseek", model_id: "deepseek-v4-pro", model_name: "DeepSeek V4 Pro", reasoning: "off", label: "DeepSeek V4 Pro", default: true },
  { key: "deepseek-v4-pro:high", provider: "deepseek", model_id: "deepseek-v4-pro", model_name: "DeepSeek V4 Pro", reasoning: "high", label: "DeepSeek V4 Pro · thinks longer", default: false },
]

it("lists the configured models with the default marked, and a pick is sent with the next message (AG-08)", () => {
  const onChange = vi.fn()
  render(<AgentModelPicker choices={choices} value={null} onChange={onChange} />)
  const select = screen.getByRole("combobox", { name: "Model for the next message" }) as HTMLSelectElement
  expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
    "DeepSeek V4 Pro (default)",
    "DeepSeek V4 Pro · thinks longer",
  ])
  expect(select.value).toBe("deepseek-v4-pro:off")
  fireEvent.change(select, { target: { value: "deepseek-v4-pro:high" } })
  expect(onChange).toHaveBeenCalledWith("deepseek-v4-pro:high")
  expect(modelParams(choices[1])).toEqual({ model: "deepseek-v4-pro", reasoning: "high" })
  expect(modelParams(choices[0])).toEqual({})
})

it("shows nothing when only one model is set up", () => {
  const { container } = render(<AgentModelPicker choices={choices.slice(0, 1)} value={null} onChange={() => {}} />)
  expect(container.innerHTML).toBe("")
})
