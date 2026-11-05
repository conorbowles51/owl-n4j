/**
 * The header job tray asks nothing while no job runs, so it is told when this tab starts one. Every request that
 * starts a long phone job matches here; fetchAPI raises the event after a successful answer.
 */
export const JOB_STARTED_EVENT = "loupe:job-started"

const STARTS_JOB =
  /^\/api\/(phones\/(exports|media\/derive-batches|media\/image-index|media\/originals|reparse)|phone-analysis\/runs|pattern\/[^/]+\/together)(\?|$)/

export function startsJob(endpoint: string, method: string | undefined): boolean {
  return method === "POST" && STARTS_JOB.test(endpoint)
}
