import { expect, it } from "vitest"
import {
  parseCorrectionFile,
  verifyBulkCorrectionResponse,
} from "./bulk-correction-file"

it("preserves commas, doubled quotes and multiple lines in the explanation", () => {
  expect(
    parseCorrectionFile(
      '\uFEFFkey,amount,reason\r\na,125.50,"Page 2, labelled ""Credit""\nChecked against PDF"\r\nb,-.25,Adjustment',
      "test.csv"
    )
  ).toEqual([
    {
      node_key: "a",
      new_amount: 125.5,
      correction_reason: 'Page 2, labelled "Credit"\nChecked against PDF',
      line: 2,
    },
    {
      node_key: "b",
      new_amount: -0.25,
      correction_reason: "Adjustment",
      line: 4,
    },
  ])
})
it("reads tab-separated records without treating commas in explanations as separators", () => {
  expect(
    parseCorrectionFile(
      "node_key\tnew_amount\tcorrection_reason\na\t1200.01\tPage 2, original total",
      "test.tsv"
    )[0].new_amount
  ).toBe(1200.01)
})
it.each([
  '"1,250.50"',
  "125.5GBP",
  "Infinity",
  "1e309",
  "0",
  "1.234",
  "9007199254740993",
  "1.234567890123456789",
])(
  "refuses an unsafe or incomplete amount %s rather than truncating it",
  (value) => {
    expect(() =>
      parseCorrectionFile(`key,amount,reason\na,${value},Checked`, "test.csv")
    ).toThrow("Line 2")
  }
)
it.each([
  ["a,1,Checked\na,2,Again", "appears more than once"],
  ["a,1,", "enter a reason"],
  ['a,1,"Unfinished', "closing quotation"],
  ["a,1,Too,many", "number of fields"],
  ['a,1,"Checked"unexpected', "quotation marks"],
])("refuses the whole invalid file: %s", (rows, message) => {
  expect(() =>
    parseCorrectionFile(`key,amount,reason\n${rows}`, "test.csv")
  ).toThrow(message)
})
it("requires named columns and rejects unsupported workbooks", () => {
  expect(() =>
    parseCorrectionFile("date,value,note\na,1,Checked", "test.csv")
  ).toThrow("key column")
  expect(() =>
    parseCorrectionFile("key,amount,reason\na,1,Checked", "test.xlsx")
  ).toThrow("Save an Excel workbook as CSV")
})
const request = [
  {
    node_key: "a",
    new_amount: 125,
    expected_amount: 100,
    correction_reason: "Checked",
  },
  {
    node_key: "b",
    new_amount: 225,
    expected_amount: 200,
    correction_reason: "Checked",
  },
]
const response = {
  success: false,
  corrected: 1,
  errors: 1,
  total: 2,
  results: [
    { key: "a", status: "corrected", old_amount: 100, new_amount: 125 },
    { key: "b", status: "error", reason: "Record changed" },
  ],
}
it("accepts an exact partial result without claiming every record was saved", () => {
  expect(verifyBulkCorrectionResponse(response, request)).toEqual(response)
})
it("refuses incomplete, duplicate or mismatched confirmation records", () => {
  for (const bad of [
    { ...response, success: true },
    { ...response, results: [response.results[0]] },
    { ...response, results: [response.results[0], response.results[0]] },
    {
      ...response,
      results: [
        { ...response.results[0], new_amount: 126 },
        response.results[1],
      ],
    },
    {
      ...response,
      results: [
        { ...response.results[0], old_amount: 99 },
        response.results[1],
      ],
    },
  ])
    expect(() => verifyBulkCorrectionResponse(bad, request)).toThrow()
})

it("requires the original unreadable text in a confirmed correction result", () => {
  const requested = [
    {
      node_key: "one",
      new_amount: 125,
      correction_reason: "Checked",
      expected_raw_amount: "not stated",
    },
  ]
  const response = {
    success: true,
    corrected: 1,
    errors: 0,
    total: 1,
    results: [
      {
        key: "one",
        status: "corrected",
        old_amount: null,
        old_raw_amount: "not stated",
        new_amount: 125,
      },
    ],
  }
  expect(verifyBulkCorrectionResponse(response, requested).corrected).toBe(1)
  expect(() =>
    verifyBulkCorrectionResponse(
      { ...response, results: [{ ...response.results[0], old_amount: 0 }] },
      requested
    )
  ).toThrow("not confirm")
  expect(() =>
    verifyBulkCorrectionResponse(
      {
        ...response,
        results: [{ ...response.results[0], old_raw_amount: "changed" }],
      },
      requested
    )
  ).toThrow("not confirm")
})
