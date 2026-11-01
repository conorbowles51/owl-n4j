import { phoneLinkSummary, type PhoneLinkLike } from "./phone-links"

/** The app, the time with its zone and the badges of a phone link, shown beside its label (07 6.4 item 11). */
export function PhoneLinkDetail({ link }: { link: PhoneLinkLike }) {
  const summary = phoneLinkSummary(link)
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground" data-testid="phone-link-detail">
      <span>{summary.kind}</span>
      {summary.app && <span>· {summary.app}</span>}
      {summary.time && <span>· {summary.time}</span>}
      {summary.badges.map((badge) => (
        <span key={badge} className="rounded border border-border px-1 py-px">
          {badge}
        </span>
      ))}
    </span>
  )
}
