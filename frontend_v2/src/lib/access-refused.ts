/**
 * Sent on window by fetchAPI for every 401 or 403 answer, with the endpoint as
 * its detail, so a holder of permissions (FinancialAccessProvider) checks them
 * again when a request is refused instead of polling for a change.
 */
export const ACCESS_REFUSED_EVENT = "loupe:access-refused"
