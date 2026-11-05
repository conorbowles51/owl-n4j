import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { lazySchema } from "@/lib/lazy-schema"

const accessSchema = lazySchema(() => z.object({
  case_id: z.string(),
  user_id: z.string(),
  can_edit: z.boolean(),
  can_upload: z.boolean(),
}))

type Owner = { id?: string | null; username?: string | null } | null | undefined

/**
 * The case access check (key and fetcher), of FinancialAccessProvider. Keyed on the signed-in person, so it is only built once the sign-in check has answered.
 */
export function financialCaseAccessQuery(caseId: string | undefined, user: Owner) {
  const owner = user?.id || user?.username
  return {
    queryKey: ["financial-case-access", owner, caseId],
    queryFn: async () => {
      const data = accessSchema.parse(
        await fetchAPI(
          `/api/financial/case-access?${new URLSearchParams({ case_id: caseId! })}`
        )
      )
      if (data.case_id !== caseId || (user?.id && data.user_id !== user.id))
        throw Error("The access response does not match this case and user.")
      return data
    },
  }
}
