import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MapPinned } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ApiError } from "@/lib/api-client"
import type { Case } from "@/types/case.types"
import { casesAPI, type AddressLookupMode } from "../api"

const OPTIONS: Array<{ value: AddressLookupMode; label: string; description: string }> = [
  {
    value: "auto",
    label: "Automatic",
    description:
      "Addresses found in evidence are sent to the OpenStreetMap address service (outside this server) on their own, one a second, and placed on the map as not confirmed.",
  },
  {
    value: "flag",
    label: "Only when a person clicks",
    description:
      "Addresses wait in the map's Needs review list. Nothing is sent until someone clicks Look up for an address, or Look up all.",
  },
]

/** Who may change the setting: the case's owner, or an admin (the server enforces the same). */
function canChangeAddressLookup(caseData: Pick<Case, "user_role" | "is_owner">) {
  return caseData.is_owner || caseData.user_role === "owner" || caseData.user_role === "admin_access"
}

/** How addresses found in a case's evidence are looked up: automatically, or only when a person clicks. */
export function AddressLookupSetting({ caseData }: { caseData: Pick<Case, "id" | "user_role" | "is_owner"> }) {
  const queryClient = useQueryClient()
  const key = ["cases", caseData.id, "address-lookup"]
  const { data, isLoading, isError } = useQuery({
    queryKey: key,
    queryFn: () => casesAPI.getAddressLookup(caseData.id),
    // while automatic lookups are working through waiting addresses, show the count going down
    refetchInterval: (query) => (query.state.data?.mode === "auto" && (query.state.data?.waiting ?? 0) > 0 ? 10000 : false),
  })
  const [error, setError] = useState<string | null>(null)
  const change = useMutation({
    mutationFn: (mode: AddressLookupMode | null) => casesAPI.setAddressLookup(caseData.id, mode),
    onSuccess: (state) => {
      setError(null)
      queryClient.setQueryData(key, state)
      void queryClient.invalidateQueries({ queryKey: ["map"] })
    },
    onError: (err) =>
      setError(
        err instanceof ApiError && err.status === 403
          ? "Only the case's owner or an admin can change this."
          : `Not changed: ${err instanceof Error ? err.message : "the server did not answer"}`
      ),
  })
  const editable = canChangeAddressLookup(caseData)

  return (
    <Card className="mt-6 gap-4 p-5">
      <CardHeader className="grid-cols-[auto_1fr] grid-rows-[auto_auto] gap-x-3">
        <div className="row-span-2 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
          <MapPinned className="size-4" />
        </div>
        <CardTitle className="self-end text-base">Address lookup</CardTitle>
        <CardDescription>
          How addresses found in this case's evidence are placed on the map. The map itself is always drawn from
          this server.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-xs text-muted-foreground">Reading the setting…</p>}
        {isError && <p className="text-xs text-destructive">The setting could not be read. Nothing has changed.</p>}
        {data && (
          <>
            <div role="radiogroup" aria-label="Address lookup" className="space-y-2">
              {OPTIONS.map((option) => {
                const selected = data.mode === option.value
                return (
                  <label
                    key={option.value}
                    className="flex cursor-pointer items-start gap-2 rounded-md border border-border p-2.5 text-sm has-[:disabled]:cursor-default"
                  >
                    <input
                      type="radio"
                      name="address-lookup"
                      value={option.value}
                      checked={selected}
                      disabled={!editable || change.isPending}
                      onChange={() => change.mutate(option.value)}
                      className="mt-1"
                    />
                    <span className="space-y-0.5">
                      <span className="flex items-center gap-2 font-medium">
                        {option.label}
                        {data.default_mode === option.value && (
                          <Badge variant="slate" className="text-[9px]">
                            System default
                          </Badge>
                        )}
                      </span>
                      <span className="block text-xs text-muted-foreground">{option.description}</span>
                    </span>
                  </label>
                )
              })}
            </div>
            <p className="text-xs text-muted-foreground" role="status">
              {data.chosen ? "Set for this case." : "This case follows the system default."}{" "}
              {data.waiting === null
                ? "The number of addresses waiting could not be read."
                : data.waiting === 0
                  ? "No addresses are waiting for a lookup."
                  : data.mode === "auto"
                    ? `${data.waiting} address${data.waiting === 1 ? " is" : "es are"} being looked up, one a second.`
                    : `${data.waiting} address${data.waiting === 1 ? " is" : "es are"} waiting in Needs review for someone to click Look up.`}
            </p>
            {data.chosen && editable && (
              <Button variant="outline" size="sm" disabled={change.isPending} onClick={() => change.mutate(null)}>
                Use the system default
              </Button>
            )}
            {!editable && (
              <p className="text-xs text-muted-foreground">Only the case's owner or an admin can change this.</p>
            )}
            {error && <p className="text-xs text-destructive">{error}</p>}
          </>
        )}
      </CardContent>
    </Card>
  )
}
