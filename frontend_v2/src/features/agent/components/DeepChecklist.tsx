import { Check, Circle, CircleDashed, MinusCircle } from "lucide-react"

import { deepLine, type DeepProgress } from "../deep-investigation"

/** The deep investigation's checklist with true counts: filled by the run as it works. */
export function DeepChecklist({ progress }: { progress: DeepProgress }) {
  return (
    <div className="mt-2 space-y-1 text-xs" data-testid="deep-checklist">
      <p className="font-medium text-foreground" data-testid="deep-checklist-line">
        {deepLine(progress)}
      </p>
      <ul className="space-y-0.5">
        {progress.items.map((item) => (
          <li key={item.id} className="flex items-start gap-1.5" data-status={item.status}>
            {item.status === "done" ? (
              <Check className="mt-0.5 size-3 shrink-0 text-emerald-600" />
            ) : item.status === "not_done" ? (
              <MinusCircle className="mt-0.5 size-3 shrink-0 text-amber-600" />
            ) : item.status === "in_progress" ? (
              <CircleDashed className="mt-0.5 size-3 shrink-0" />
            ) : (
              <Circle className="mt-0.5 size-3 shrink-0 opacity-50" />
            )}
            <span>
              {item.title}
              {item.of ? ` (${item.covered} of ${item.of})` : ""}
              {item.status === "not_done" && item.reason ? `: not done, ${item.reason}` : ""}
            </span>
          </li>
        ))}
      </ul>
      {progress.analyses && progress.analyses.length > 0 ? (
        <p>
          Stored analyses:{" "}
          {progress.analyses.map((a) => `${a.approach.replace(/_/g, " ")} ${a.created ? "requested" : (a.status ?? "")}`).join("; ")}.
        </p>
      ) : null}
    </div>
  )
}
