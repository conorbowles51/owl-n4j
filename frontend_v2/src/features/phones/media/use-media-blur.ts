import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { getSettings, putOwnBlur } from "../api"
import { BLUR_KEY, blurFor } from "./media-tools"

function stored(): string | null {
  try {
    return localStorage.getItem(BLUR_KEY)
  } catch {
    return null
  }
}

/**
 * Whether this person's pictures start blurred in this case (03 section 8.3, 07 section 4.11): their own choice, held
 * on the server so it follows them; else what this browser kept before there was one; else the case default.
 * Pictures stay blurred while the setting loads or cannot be read.
 */
export function useMediaBlur(caseId: string) {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ["phone-settings", caseId], queryFn: () => getSettings(caseId), enabled: !!caseId })
  const [kept, setKept] = useState(stored)
  const save = useMutation({
    mutationFn: (on: boolean) => putOwnBlur(caseId, on),
    onSuccess: (s) => qc.setQueryData(["phone-settings", caseId], s),
  })
  const own = settings.data?.own_media_blur
  const on = own === true || own === false ? own : blurFor(kept, settings.data?.media_blur?.default_on)
  return {
    on,
    caseDefault: settings.data?.media_blur,
    saving: save.isPending,
    error: save.isError ? "Your choice is kept on this browser only: it could not be saved to your account." : null,
    choose: (v: boolean) => {
      const word = v ? "on" : "off"
      setKept(word)
      try {
        localStorage.setItem(BLUR_KEY, word)
      } catch {
        /* storage unavailable: the server holds the choice */
      }
      save.mutate(v)
    },
  }
}
