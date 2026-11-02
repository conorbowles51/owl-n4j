import type { Meta, StoryObj } from "@storybook/react-vite"
import { Badge } from "../badge"
import { CheckTag, DirectionMark, MONEY, ShareBar, SourceTag, appTone } from "@/lib/data-colour"
import { BalanceMove } from "@/features/financial/components/AccountHistory"

/**
 * lx-style data colour (Neil 2 Nov 2026, mock2): money in and out, sources, apps, kinds, bars and the "needs a
 * check" tag, as they appear inside the content of the busy screens, on the page, card and muted surfaces. Light
 * and dark.
 */
const meta = { title: "Style/Data colour", parameters: { layout: "padded" } } satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const Row = ({ surface }: { surface: string }) => (
  <div className={`flex flex-wrap items-center gap-3 p-2 ${surface}`}>
    <span className={`text-sm font-semibold ${MONEY.in.text}`}>↓ +1,050.00 USD</span>
    <DirectionMark direction="in" />
    <span className={`text-sm font-semibold ${MONEY.out.text}`}>↑ −250.00 USD</span>
    <DirectionMark direction="out" />
    {["acct-1", "acct-2", "acct-3", "acct-4", "acct-5"].map((key) => (
      <SourceTag key={key} sourceKey={key}>
        Monex · {key}
      </SourceTag>
    ))}
    {["WhatsApp", "Telegram", "Signal", "Native Messages"].map((app) => (
      <span key={app} className={`rounded border px-1.5 text-xs font-semibold ${appTone(app).text} ${appTone(app).border}`}>
        {app}
      </span>
    ))}
    <CheckTag />
    <CheckTag>Amount unknown · check source</CheckTag>
    <Badge variant="success">✓ Reconciled</Badge>
    <span className="text-status-neutral">Confirmed quiet period</span>
    <span className="text-xs text-status-info">12.00</span>
    <span className="text-xs">
      <BalanceMove opening="100" closing="200" />
      200.00 <BalanceMove opening="200" closing="100" /> 100.00
    </span>
    <span className="text-xs">
      52 / 65
      <ShareBar value={52} max={65} />
    </span>
    {(["text-source-1", "text-source-2", "text-source-3", "text-source-4"] as const).map((c, i) => (
      <span key={c} className={`rounded-full border px-2 text-[10px] font-bold ${c}`}>
        {["Statements", "Gaps", "Document", "Phone"][i]}
      </span>
    ))}
  </div>
)

const Set = () => (
  <main className="flex flex-col gap-3 bg-background p-4 text-foreground">
    <Row surface="" />
    <Row surface="bg-card" />
    <Row surface="bg-muted" />
    <div className="flex items-center gap-2 rounded border border-l-4 border-status-warning bg-status-warning-soft px-3 py-2 text-sm">
      <CheckTag />
      <span>
        <strong>4,745</strong> payments in view with the other side not identified
      </span>
    </div>
    <div className="bg-status-info-soft px-3 py-1.5 text-sm shadow-[inset_4px_0_0_hsl(var(--status-info))]">
      <span className="font-medium">10:42</span> Sent: see you at the bank at noon
    </div>
  </main>
)

export const DataColourLight: Story = { render: Set, parameters: { theme: "light" } }
export const DataColourDark: Story = { render: Set, parameters: { theme: "dark" } }
