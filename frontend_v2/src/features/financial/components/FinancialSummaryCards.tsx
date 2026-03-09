import { TrendingUp, TrendingDown, ArrowLeftRight, Users } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { CostBadge } from "@/components/ui/cost-badge"
import type { FinancialSummary } from "../api"

interface FinancialSummaryCardsProps {
  summary: FinancialSummary
}

export function FinancialSummaryCards({ summary }: FinancialSummaryCardsProps) {
  const cards = [
    {
      label: "Total Inflow",
      value: summary.total_inflow,
      icon: TrendingUp,
      color: "text-emerald-500",
    },
    {
      label: "Total Outflow",
      value: summary.total_outflow,
      icon: TrendingDown,
      color: "text-red-500",
    },
    {
      label: "Net Flow",
      value: summary.net_flow,
      icon: ArrowLeftRight,
      color: summary.net_flow >= 0 ? "text-emerald-500" : "text-red-500",
    },
    {
      label: "Transactions",
      value: summary.transaction_count,
      icon: Users,
      isCount: true,
    },
  ]

  return (
    <div className="grid grid-cols-4 gap-3">
      {cards.map((card) => (
        <Card key={card.label} className="p-3">
          <CardContent className="flex items-center gap-3 p-0">
            <div className={card.color || "text-muted-foreground"}>
              <card.icon className="size-4" />
            </div>
            <div>
              <p className="text-[10px] text-muted-foreground">{card.label}</p>
              {card.isCount ? (
                <span className="font-mono text-sm font-semibold">
                  {card.value.toLocaleString()}
                </span>
              ) : (
                <CostBadge amount={card.value as number} />
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
