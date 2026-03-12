import { useMemo } from "react"
import { TrendingUp, TrendingDown, ArrowLeftRight, Hash, User } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { CostBadge } from "@/components/ui/cost-badge"
import type { Transaction } from "../api"

interface FinancialSummaryCardsProps {
  transactions: Transaction[]
  entityFilter: { key: string; name: string } | null
}

export function FinancialSummaryCards({
  transactions,
  entityFilter,
}: FinancialSummaryCardsProps) {
  const summary = useMemo(() => {
    if (entityFilter) {
      let inflow = 0
      let outflow = 0
      for (const tx of transactions) {
        const isTo =
          tx.to_entity?.key === entityFilter.key ||
          tx.to_entity?.name === entityFilter.name
        const isFrom =
          tx.from_entity?.key === entityFilter.key ||
          tx.from_entity?.name === entityFilter.name
        if (isTo) inflow += Math.abs(tx.amount)
        if (isFrom) outflow += Math.abs(tx.amount)
      }
      return {
        mode: "entity" as const,
        entityName: entityFilter.name,
        inflow,
        outflow,
        netFlow: inflow - outflow,
        count: transactions.length,
      }
    }

    let totalVolume = 0
    const entityKeys = new Set<string>()
    for (const tx of transactions) {
      totalVolume += Math.abs(tx.amount)
      if (tx.from_entity?.key) entityKeys.add(tx.from_entity.key)
      else if (tx.from_entity?.name) entityKeys.add(`n:${tx.from_entity.name}`)
      if (tx.to_entity?.key) entityKeys.add(tx.to_entity.key)
      else if (tx.to_entity?.name) entityKeys.add(`n:${tx.to_entity.name}`)
    }

    return {
      mode: "overview" as const,
      totalVolume,
      count: transactions.length,
      uniqueEntities: entityKeys.size,
      avgTransaction: transactions.length > 0 ? totalVolume / transactions.length : 0,
    }
  }, [transactions, entityFilter])

  if (summary.mode === "entity") {
    const cards = [
      {
        label: `Inflows — ${summary.entityName}`,
        value: summary.inflow,
        icon: TrendingUp,
        color: "text-emerald-500",
      },
      {
        label: `Outflows — ${summary.entityName}`,
        value: summary.outflow,
        icon: TrendingDown,
        color: "text-red-500",
      },
      {
        label: "Net Flow",
        value: summary.netFlow,
        icon: ArrowLeftRight,
        color: summary.netFlow >= 0 ? "text-emerald-500" : "text-red-500",
      },
      {
        label: "Transactions",
        value: summary.count,
        icon: Hash,
        isCount: true,
      },
    ]

    return <SummaryGrid cards={cards} />
  }

  const cards = [
    {
      label: "Total Volume",
      value: summary.totalVolume,
      icon: ArrowLeftRight,
      color: "text-amber-500",
    },
    {
      label: "Transactions",
      value: summary.count,
      icon: Hash,
      isCount: true,
    },
    {
      label: "Unique Entities",
      value: summary.uniqueEntities,
      icon: User,
      isCount: true,
    },
    {
      label: "Avg Transaction",
      value: summary.avgTransaction,
      icon: TrendingUp,
      color: "text-blue-500",
    },
  ]

  return <SummaryGrid cards={cards} />
}

interface CardData {
  label: string
  value: number
  icon: React.ComponentType<{ className?: string }>
  color?: string
  isCount?: boolean
}

function SummaryGrid({ cards }: { cards: CardData[] }) {
  return (
    <div className="grid grid-cols-4 gap-3 px-4 py-3">
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
                <CostBadge amount={card.value} />
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
