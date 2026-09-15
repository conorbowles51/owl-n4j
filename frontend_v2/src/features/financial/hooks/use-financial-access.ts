import { createContext, useContext } from "react"

export type FinancialAccess = {
  canEdit: boolean
  canUpload: boolean
  ready: boolean
  error: boolean
  retry?: () => void
}

export const FinancialAccessContext = createContext<FinancialAccess>({
  canEdit: false,
  canUpload: false,
  ready: false,
  error: false,
})

export function useFinancialAccess() {
  return useContext(FinancialAccessContext)
}
