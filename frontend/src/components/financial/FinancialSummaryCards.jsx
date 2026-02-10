import { TrendingUp, TrendingDown, DollarSign, Hash, Users } from 'lucide-react';

function formatCurrency(amount) {
  if (amount == null) return '$0.00';
  const absVal = Math.abs(amount);
  if (absVal >= 1_000_000) return `$${(absVal / 1_000_000).toFixed(2)}M`;
  if (absVal >= 1_000) return `$${(absVal / 1_000).toFixed(1)}K`;
  return `$${absVal.toFixed(2)}`;
}

export default function FinancialSummaryCards({ summary, entityFilter }) {
  if (!summary) return null;

  const cards = entityFilter
    ? [
        {
          label: 'Inflows',
          value: formatCurrency(summary.total_inflows),
          icon: TrendingUp,
          color: '#22c55e',
          bgColor: '#22c55e10',
        },
        {
          label: 'Outflows',
          value: formatCurrency(summary.total_outflows),
          icon: TrendingDown,
          color: '#ef4444',
          bgColor: '#ef444410',
        },
        {
          label: 'Net Flow',
          value: formatCurrency(summary.net_flow),
          icon: DollarSign,
          color: summary.net_flow >= 0 ? '#22c55e' : '#ef4444',
          bgColor: summary.net_flow >= 0 ? '#22c55e10' : '#ef444410',
        },
        {
          label: 'Transactions',
          value: summary.transaction_count?.toLocaleString() || '0',
          icon: Hash,
          color: '#3b82f6',
          bgColor: '#3b82f610',
        },
      ]
    : [
        {
          label: 'Total Volume',
          value: formatCurrency(summary.total_volume),
          icon: DollarSign,
          color: '#3b82f6',
          bgColor: '#3b82f610',
        },
        {
          label: 'Transactions',
          value: summary.transaction_count?.toLocaleString() || '0',
          icon: Hash,
          color: '#3b82f6',
          bgColor: '#3b82f610',
        },
        {
          label: 'Unique Entities',
          value: summary.unique_entities?.toLocaleString() || '0',
          icon: Users,
          color: '#8b5cf6',
          bgColor: '#8b5cf610',
        },
        {
          label: 'Avg Transaction',
          value: formatCurrency(summary.avg_amount),
          icon: DollarSign,
          color: '#6b7280',
          bgColor: '#6b728010',
        },
      ];

  return (
    <div>
      {entityFilter && (
        <div className="text-xs text-light-500 mb-1.5">
          Showing flows relative to <span className="font-medium text-light-700">{entityFilter.name}</span>
        </div>
      )}
      <div className="grid grid-cols-4 gap-3">
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
                <span className="text-xs text-light-600">{card.label}</span>
              </div>
              <div className="text-lg font-semibold" style={{ color: card.color }}>
                {card.value}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
