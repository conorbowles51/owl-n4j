import { useCallback, useMemo } from "react"
import { useSearchParams } from "react-router-dom"
import { phoneLayersEnabled, toChosen } from "../lib/phone-layers"
import { useCasePhones } from "./use-case-phones"

/** A screen's phone layers (`keepAll` writes every phone out in full, for a screen where an empty list means this phone) in its address (`phones=<id>,<id>`; empty is every phone): the phones of the case, the
 * ones chosen, and the setter. `enabled` is the phone_layers setting. */
export function usePhoneLayerParam(caseId: string) {
  const [search, setSearch] = useSearchParams()
  const phones = useCasePhones(caseId)
  const enabled = phoneLayersEnabled()
  const chosen = useMemo(() => (enabled ? (search.get("phones") ?? "").split(",").filter(Boolean) : []), [enabled, search])
  const set = useCallback((ids: string[], keepAll = false) => {
    setSearch((prev) => {
      const next = new URLSearchParams(prev)
      const c = keepAll ? ids : toChosen(phones.map((p) => p.id), ids)
      if (c.length) next.set("phones", c.join(","))
      else next.delete("phones")
      return next
    }, { replace: true })
  }, [phones, setSearch])
  return { enabled, phones, chosen, set }
}
