import type { TutorialStep } from "../types"
import { MONEY } from "./money"

/** Every workflow's steps, by the workflow's id in catalogue.ts. */
export const TUTORIALS: Record<string, TutorialStep[]> = {
  money: MONEY,
}
