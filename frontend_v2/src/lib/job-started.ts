/**
 * The header job tray asks nothing while no job runs, so it is told when this tab starts one: fetchAPI raises the
 * event after a successful answer to a request listed here. Work begun elsewhere (another person, or a phone whose
 * upload finishes by itself) is seen the next time a screen changes or the tab is returned to.
 */
export const JOB_STARTED_EVENT = "loupe:job-started"

const STARTS_JOB = new RegExp(
  "^/api/(" +
    "phones/(exports|media/derive-batches|media/image-index|media/originals|reparse)" +
    "|phones/readings/([^/]+/(confirm|correct)|confirm-kind)" + // a decision reads the phone again
    "|phones/[^/]+/(clock-offset|default-region|device-zone|offsetless-zone)" +
    "|phone-analysis/runs" +
    "|pattern/[^/]+/together" +
    "|evidence/process(/background)?" +
    ")(\\?|$)"
)

export function startsJob(endpoint: string, method: string | undefined): boolean {
  return method === "POST" && STARTS_JOB.test(endpoint)
}
