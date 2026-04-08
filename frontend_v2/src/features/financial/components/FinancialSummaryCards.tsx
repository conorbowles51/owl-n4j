import { useMemo } from "react"
import { ArrowDownLeft, ArrowUpRight, Hash, User } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { CostBadge } from "@/components/ui/cost-badge"
import type { Transaction, FinancialDatasetMode } from "../api"

interface FinancialSummaryCardsProps {
  transactions: Transaction[]
  mode: FinancialDatasetMode
}

export function FinancialSummaryCards({
  transactions,
  mode,
}: FinancialSummaryCardsProps) {
  const summary = useMemo(() => {
    let moneyOut = 0
    let moneyIn = 0
    const entityKeys = new Set<string>()

    for (const tx of transactions) {
      if (tx.amount >= 0) moneyOut += Math.abs(tx.amount)
      else moneyIn += Math.abs(tx.amount)

      if (tx.from_entity?.key) entityKeys.add(tx.from_entity.key)
      else if (tx.from_entity?.name) entityKeys.add(`n:${tx.from_entity.name}`)

      if (tx.to_entity?.key) entityKeys.add(tx.to_entity.key)
      else if (tx.to_entity?.name) entityKeys.add(`n:${tx.to_entity.name}`)
    }

    return {
      moneyOut,
      moneyIn,
      count: transactions.length,
      uniqueEntities: entityKeys.size,
    }
  }, [transactions])

  const cards = [
    {
      label: "Money Out",
      description: "Positive amounts",
      value: summary.moneyOut,
      icon: ArrowUpRight,
      color: "text-red-500",
    },
    {
      label: "Money In",
      description: "Negative amounts",
      value: summary.moneyIn,
      icon: ArrowDownLeft,
      color: "text-emerald-500",
    },
    {
      label: mode === "transactions" ? "Transactions" : "Records",
      description: "Filtered total",
      value: summary.count,
      icon: Hash,
      isCount: true,
    },
    {
      label: "Unique Entities",
      description: "Visible counterparties",
      value: summary.uniqueEntities,
      icon: User,
      isCount: true,
    },
  ]

  return <SummaryGrid cards={cards} />
}

interface CardData {
  label: string
  description: string
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
              <p className="text-[10px] text-muted-foreground">
                {card.description}
              </p>
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
