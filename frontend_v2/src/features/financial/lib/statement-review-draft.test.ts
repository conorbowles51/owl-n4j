import { beforeEach, expect, it } from "vitest"
import { readStatementDraft, saveStatementDraft, type StatementDraft } from "./statement-review-draft"
const draft: StatementDraft = {revision:"first", rows:[{id:"1:0:2",excluded:false,date:"",description:"Unfinished correction",counterparty:"",amount_minor:"",direction:"debit",balance_minor:null,reason:"Checking source"}],holder:"Holder",account:"Account",institution:"Bank",periodStart:"",periodEnd:"",detailsReason:"",amountText:{"1:0:2":"12."}}
beforeEach(()=>sessionStorage.clear())
it("restores incomplete edits exactly after a refresh",()=>{
  expect(saveStatementDraft("user:case:file:first",draft)).toBe(true)
  expect(readStatementDraft("user:case:file:first","first")).toEqual(draft)
})
it("does not apply edits to a changed extraction or another user's scope",()=>{
  saveStatementDraft("user:case:file:first",draft)
  expect(readStatementDraft("user:case:file:first","second")).toBeNull()
  expect(readStatementDraft("other-user:case:file:first","first")).toBeNull()
})
it("ignores malformed saved data without losing the current review",()=>{
  sessionStorage.setItem("draft",'{"rows":"broken"}')
  expect(readStatementDraft("draft","first")).toBeNull()
  expect(readStatementDraft(null,"first")).toBeNull()
})
