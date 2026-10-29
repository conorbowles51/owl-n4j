import { expect, it } from "vitest"
import { categoryList, matchesCategories } from "./use-payment-categories"

it("reads old single-category values and new lists alike", () => {
  expect(categoryList("")).toEqual([])
  expect(categoryList("Rent")).toEqual(["Rent"])
  expect(categoryList(["Rent", "Rent", "", 3, "Payroll"])).toEqual(["Rent", "Payroll"])
  expect(categoryList(undefined)).toEqual([])
})

it("an empty choice keeps every payment; otherwise any chosen category matches", () => {
  expect(matchesCategories({ category: "Rent" }, [])).toBe(true)
  expect(matchesCategories({}, ["Uncategorized", "Rent"])).toBe(true)
  expect(matchesCategories({ category: "Payroll" }, ["Rent"])).toBe(false)
})
