/**
 * The case's phones (GET /api/phones), shared by the sidebar and the Phones page.
 * The phones API module (and its schema library) loads with this query, not with the shell.
 */
export const phonesQuery = (caseId: string | undefined) => ({
  queryKey: ["phones", caseId],
  queryFn: () => import("@/features/phones/api").then((m) => m.getPhones(caseId!)),
})
