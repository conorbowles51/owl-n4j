import { ArrowUpRight, ArrowDownLeft, Hash, Users } from 'lucide-react';

function formatCurrency(amount) {
  if (amount == null) return '$0.00';
  const absVal = Math.abs(amount);
  if (absVal >= 1_000_000) return `$${(absVal / 1_000_000).toFixed(2)}M`;
  if (absVal >= 1_000) return `$${(absVal / 1_000).toFixed(1)}K`;
  return `$${absVal.toFixed(2)}`;
}

/**
 * FinancialSummaryCards
 *
 * Simple, consistent display of two primary numbers:
 *   - Money Out: sum of positive-amount transactions (debits/spending)
 *   - Money In:  sum of negative-amount transactions (credits/refunds)
 *
 * Plus secondary context cards (transactions, unique entities).
 *
 * The same labels apply whether or not entities are selected — entity
 * selection just filters which transactions are included.
 */
export default function FinancialSummaryCards({ summary, hasEntitySelection, entitySelectionLabel }) {
  if (!summary) return null;

  // Sign-based totals (always present from filteredSummary):
  //   total_outflows = sum of positive amounts → "Money Out"
  //   total_inflows  = sum of negative amounts (abs) → "Money In"
  const moneyOut = summary.total_outflows || 0;
  const moneyIn = summary.total_inflows || 0;
  const txnCount = summary.transaction_count || 0;
  const uniqueEntities = summary.unique_entities;

  const cards = [
    {
      label: 'Money Out',
      sublabel: 'Positive transactions',
      value: formatCurrency(moneyOut),
      icon: ArrowUpRight,
      color: '#dc2626',
      bgColor: '#fef2f2',
    },
    {
      label: 'Money In',
      sublabel: 'Negative transactions',
      value: formatCurrency(moneyIn),
      icon: ArrowDownLeft,
      color: '#16a34a',
      bgColor: '#dcfce7',
    },
    {
      label: 'Transactions',
      sublabel: hasEntitySelection ? 'Filtered' : 'Total',
      value: txnCount.toLocaleString(),
      icon: Hash,
      color: '#3b82f6',
      bgColor: '#eff6ff',
    },
  ];

  // Show unique-entities card only in overview mode (it's always derived there)
  if (!hasEntitySelection && uniqueEntities != null) {
    cards.push({
      label: 'Unique Entities',
      sublabel: 'Senders + recipients',
      value: uniqueEntities.toLocaleString(),
      icon: Users,
      color: '#8b5cf6',
      bgColor: '#f5f3ff',
    });
  }

  const gridCols = cards.length === 4 ? 'grid-cols-4' : 'grid-cols-3';

  return (
    <div>
      {hasEntitySelection && entitySelectionLabel && (
        <div className="text-xs text-light-500 mb-1.5">
          Showing flows for <span className="font-medium text-light-700">{entitySelectionLabel}</span>
        </div>
      )}
      <div className={`grid ${gridCols} gap-3`}>
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className="rounded-lg border border-light-200 p-3"
              style={{ backgroundColor: card.bgColor }}
            >
              <div className="flex items-center gap-2 mb-1">
                <Icon className="w-4 h-4" style={{ color: card.color }} />
                <span className="text-xs text-light-700 font-medium">{card.label}</span>
                <span className="text-[10px] text-light-400 ml-auto">{card.sublabel}</span>
              </div>
              <div className="text-xl font-bold" style={{ color: card.color }}>
                {card.value}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
