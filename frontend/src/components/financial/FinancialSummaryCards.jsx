import { ArrowUpRight, ArrowDownLeft, Hash, Users, Repeat, TrendingUp } from 'lucide-react';

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
 * Always shows two sign-of-amount totals:
 *   - Payments: sum of positive-amount transactions (money sent / debits)
 *   - Receipts: sum of negative-amount transactions (money received / credits)
 * These are raw ledger sums — NOT perspective-based cash flow. The labels
 * apply whether or not entities are selected; entity selection just filters
 * which transactions are included.
 *
 * When `moneyFlowSummary` is provided (perspective selection active) we
 * ADDITIONALLY render Inflow / Outflow / Internal cards that measure true
 * cash flow relative to the selected perspective entities. These coexist
 * with Payments/Receipts and are never confused with them.
 */
export default function FinancialSummaryCards({
  summary,
  hasEntitySelection,
  entitySelectionLabel,
  moneyFlowSummary,
  hasMoneyFlowSelection,
  moneyFlowLabel,
}) {
  if (!summary) return null;

  // Sign-based totals (always present from filteredSummary):
  //   total_outflows = sum of positive amounts → "Payments"
  //   total_inflows  = sum of negative amounts (abs) → "Receipts"
  const payments = summary.total_outflows || 0;
  const receipts = summary.total_inflows || 0;
  const txnCount = summary.transaction_count || 0;
  const uniqueEntities = summary.unique_entities;

  const cards = [
    {
      label: 'Payments',
      sublabel: 'Sent (positive)',
      value: formatCurrency(payments),
      icon: ArrowUpRight,
      color: '#dc2626',
      bgColor: '#fef2f2',
    },
    {
      label: 'Receipts',
      sublabel: 'Received (negative)',
      value: formatCurrency(receipts),
      icon: ArrowDownLeft,
      color: '#16a34a',
      bgColor: '#dcfce7',
    },
  ];

  // When a Money Flow perspective is active, insert true cash-flow cards
  // alongside the raw ledger sums.
  if (hasMoneyFlowSelection && moneyFlowSummary) {
    cards.push({
      label: 'Inflow',
      sublabel: 'Into perspective',
      value: formatCurrency(moneyFlowSummary.inflow || 0),
      icon: ArrowDownLeft,
      color: '#0ea5e9',
      bgColor: '#e0f2fe',
    });
    cards.push({
      label: 'Outflow',
      sublabel: 'Out of perspective',
      value: formatCurrency(moneyFlowSummary.outflow || 0),
      icon: ArrowUpRight,
      color: '#ea580c',
      bgColor: '#fff7ed',
    });
    if ((moneyFlowSummary.internal || 0) > 0) {
      cards.push({
        label: 'Internal',
        sublabel: 'Intra-set',
        value: formatCurrency(moneyFlowSummary.internal || 0),
        icon: Repeat,
        color: '#64748b',
        bgColor: '#f1f5f9',
      });
    }
  }

  cards.push({
    label: 'Transactions',
    sublabel: (hasEntitySelection || hasMoneyFlowSelection) ? 'Filtered' : 'Total',
    value: txnCount.toLocaleString(),
    icon: Hash,
    color: '#3b82f6',
    bgColor: '#eff6ff',
  });

  // Show unique-entities card only in pure overview mode (no filters of any kind)
  if (!hasEntitySelection && !hasMoneyFlowSelection && uniqueEntities != null) {
    cards.push({
      label: 'Unique Entities',
      sublabel: 'Senders + recipients',
      value: uniqueEntities.toLocaleString(),
      icon: Users,
      color: '#8b5cf6',
      bgColor: '#f5f3ff',
    });
  }

  // Inline style sidesteps Tailwind JIT class-generation for arbitrary counts
  const gridStyle = { gridTemplateColumns: `repeat(${cards.length}, minmax(0, 1fr))` };

  // Build context line: combine any active scopes
  const contextBits = [];
  if (hasEntitySelection && entitySelectionLabel) {
    contextBits.push(
      <span key="cross">
        Cross-filter: <span className="font-medium text-light-700">{entitySelectionLabel}</span>
      </span>
    );
  }
  if (hasMoneyFlowSelection && moneyFlowLabel) {
    contextBits.push(
      <span key="mf">
        Money Flow: <span className="font-medium text-owl-blue-700">{moneyFlowLabel}</span>
      </span>
    );
  }

  return (
    <div>
      {contextBits.length > 0 && (
        <div className="text-xs text-light-500 mb-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
          {contextBits}
        </div>
      )}
      <div className="grid gap-3" style={gridStyle}>
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
