import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { TransactionNote } from "./TransactionNote"
const save=vi.hoisted(()=>({mutate:vi.fn(),isPending:false,isSuccess:false,isError:false,error:new Error("Connection interrupted"),data:{case_id:"case"}}))
vi.mock("@/features/workspace/hooks/use-casework",()=>({useCreateCaseworkEntry:()=>save}))
beforeEach(()=>{save.mutate.mockReset();save.isPending=false;save.isSuccess=false;save.isError=false})
function mount(){render(<TransactionNote caseId="case" transactionId="transaction" refId="retained-reference" fileId="evidence" filename="statement.pdf" locator={{kind:"page_only",page:3}} initialOpen/>)}
it("saves the investigator's words with the exact transaction and evidence reference",()=>{
 mount();expect(screen.getByRole("button",{name:"Save investigation note"})).toBeDisabled()
 fireEvent.change(screen.getByLabelText("Your transaction note"),{target:{value:"Ask the account holder about this payment."}})
 fireEvent.click(screen.getByRole("button",{name:"Save investigation note"}))
 expect(save.mutate).toHaveBeenCalledWith(expect.objectContaining({entry_type:"note",body:"Ask the account holder about this payment.",links:[expect.objectContaining({target_type:"evidence",target_id:"evidence",source_anchor:{financial_transaction_ids:["transaction"],financial_ref_ids:["retained-reference"],locator:{kind:"page_only",page:3}}})]}))
})
it("keeps entered text available after an unsuccessful save",()=>{
 save.isError=true;mount();fireEvent.change(screen.getByLabelText("Your transaction note"),{target:{value:"Keep this investigation note."}})
 expect(screen.getByLabelText("Your transaction note")).toHaveValue("Keep this investigation note.")
 expect(screen.getByRole("alert")).toHaveTextContent("Check Workspace before trying again")
})
