import { useQuery } from "@tanstack/react-query"
import { casesAPI } from "../api"

/** Whether Deleted items are switched on (a server setting, off by default). Off, deleting a case or an evidence
 * file is immediate and no Deleted items, Restore or retention wording shows anywhere. Unknown counts as off. */
export function useDeletedItemsEnabled(): boolean {
  const query = useQuery({
    queryKey: ["deleted-items-enabled"],
    queryFn: casesAPI.listDeleted,
    staleTime: 5 * 60 * 1000,
    select: (data) => data.enabled === true,
  })
  return query.data === true
}
