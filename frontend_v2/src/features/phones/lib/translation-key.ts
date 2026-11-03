/** The query key of one source's machine translation (05 17.5); `["phone-translation", caseId]` refreshes every one
 * shown. */
export const translationKey = (caseId: string, sourceKey: string) => ["phone-translation", caseId, sourceKey]
