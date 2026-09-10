import {render, screen} from "@testing-library/react"
import {it,expect} from "vitest"
import {printedTotalChecks} from "../lib/printed-total-checks"
import {PrintedTotalChecks} from "./PrintedTotalChecks"
const capture = {limitation:"Selected readings only",checks:[
 {role:"credits_total",status:"unbalanced",printed_minor:"9007199254740993",current_minor:"9007199254740994",difference_minor:"1",source:{role:"credits_total",original_text:"Printed incoming total",reviewed_value:"9007199254740993",locator:{}}},
 {role:"debits_total",status:"unavailable",printed_minor:null,current_minor:"0",difference_minor:null,source:null}
]}
it("shows exact difference, original text and an unknown control separately from zero",()=>{
 render(<PrintedTotalChecks checks={printedTotalChecks.parse(capture)} currency="GBP" />)
 expect(screen.getByText(/Difference: 0.01 GBP/)).toBeInTheDocument()
 expect(screen.getByText(/Original control text: Printed incoming total/)).toBeInTheDocument()
 expect(screen.getByText(/Money out: No printed total recorded/)).toBeInTheDocument()
})
it("refuses inconsistent control arithmetic, source values and duplicate sides",()=>{
 for (const changed of [
 {...capture,checks:[{...capture.checks[0],difference_minor:"0"},capture.checks[1]]},
 {...capture,checks:[{...capture.checks[0],source:{...capture.checks[0].source,reviewed_value:"1"}},capture.checks[1]]},
 {...capture,checks:[capture.checks[0],capture.checks[0]]}
 ]) expect(printedTotalChecks.safeParse(changed).success).toBe(false)
})
