import type { ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import {
  FinancialAccessContext,
  useFinancialAccess,
} from "../hooks/use-financial-access"

const accessSchema = z.object({
  case_id: z.string(),
  user_id: z.string(),
  can_edit: z.boolean(),
  can_upload: z.boolean(),
})

export function FinancialAccessProvider({
  caseId,
  children,
  quietFailure = false,
}: {
  caseId: string | undefined
  children: ReactNode
  quietFailure?: boolean
}) {
  const user = useAuthStore((state) => state.user)
  const owner = user?.id || user?.username
  const query = useQuery({
    queryKey: ["financial-case-access", owner, caseId],
    enabled: !!caseId && !!owner,
    retry: false,
    staleTime: 30_000,
    refetchInterval: 30_000,
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
  })
  const status =
    query.error && "status" in query.error ? query.error.status : undefined
  const failure =
    status === 401
      ? "expired"
      : status === 403 || status === 404
        ? "denied"
        : undefined
  const ready =
    !!owner &&
    !!caseId &&
    query.isSuccess &&
    !query.isError &&
    query.data?.case_id === caseId
  return (
    <FinancialAccessContext.Provider
      value={{
        canEdit: ready && query.data?.can_edit === true,
        canUpload: ready && query.data?.can_upload === true,
        ready,
        error: query.isError,
        failure,
        retry: () => {
          void query.refetch()
        },
      }}
    >
      {failure ? quietFailure ? null : <FinancialAccessNotice /> : children}
    </FinancialAccessContext.Provider>
  )
}

export function FinancialAccessNotice() {
  const access = useFinancialAccess()
  if (access.ready && access.canEdit && access.canUpload) return null
  return (
    <div
      className="border-b px-4 py-2 text-sm"
      role={access.error ? "alert" : "status"}
    >
      {access.failure === "expired" ? (
        <>
          Your session has expired. Sign in again to continue. Unfinished
          statement work stays in this browser tab.
          <Button asChild variant="outline" size="sm" className="ml-2">
            <a href="/login">Sign in again</a>
          </Button>
        </>
      ) : access.failure === "denied" ? (
        <>
          This case is no longer available to your account. Ask the case owner
          to check your access.
          <Button asChild variant="outline" size="sm" className="ml-2">
            <a href="/cases">Open cases</a>
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="ml-2"
            onClick={access.retry}
          >
            Check access again
          </Button>
        </>
      ) : access.error ? (
        <>
          Case access could not be checked. Editing and uploads are unavailable
          until access is confirmed.
          <Button
            variant="outline"
            size="sm"
            className="ml-2"
            onClick={access.retry}
          >
            Check access again
          </Button>
        </>
      ) : !access.ready ? (
        "Checking case access…"
      ) : access.canEdit ? (
        "You can edit this case, but your access does not allow new files to be uploaded."
      ) : access.canUpload ? (
        "You can upload and read statements. Importing transactions and saving changes require case editing access."
      ) : (
        "This case is read-only. You can inspect statements, explore payments and download saved reports. A case owner can grant editing access."
      )}
    </div>
  )
}
