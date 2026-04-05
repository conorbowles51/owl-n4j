import { TrendingUp, TrendingDown, DollarSign, Hash, Users } from 'lucide-react';

function formatCurrency(amount) {
  if (amount == null) return '$0.00';
  const absVal = Math.abs(amount);
  if (absVal >= 1_000_000) return `$${(absVal / 1_000_000).toFixed(2)}M`;
  if (absVal >= 1_000) return `$${(absVal / 1_000).toFixed(1)}K`;
  return `$${absVal.toFixed(2)}`;
}

export default function FinancialSummaryCards({ summary, hasEntitySelection, entitySelectionLabel }) {
  if (!summary) return null;

  const cards = hasEntitySelection
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

  // Entity-level flow breakdown (only populated when entities are selected)
  const inflowEntities = summary.inflow_entities || null;
  const outflowEntities = summary.outflow_entities || null;

  // Inflow vs outflow comparison bar — always visible when there's flow data
  const totalInflows = summary.total_inflows || 0;
  const totalOutflows = summary.total_outflows || 0;
  const showFlowBar = totalInflows > 0 || totalOutflows > 0;
  const flowTotal = totalInflows + totalOutflows;
  const inPct = flowTotal > 0 ? (totalInflows / flowTotal) * 100 : 50;
  const outPct = 100 - inPct;
  const netFlow = totalInflows - totalOutflows;

  return (
    <div>
      {hasEntitySelection && entitySelectionLabel && (
        <div className="text-xs text-light-500 mb-1.5">
          Showing flows for <span className="font-medium text-light-700">{entitySelectionLabel}</span>
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

      {/* Inflow vs Outflow comparison bar */}
      {showFlowBar && (
        <div className="mt-2 rounded-lg border border-light-200 bg-white p-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="text-[10px] text-light-500 uppercase tracking-wider font-semibold">Inflow vs Outflow</div>
            {!hasEntitySelection && totalOutflows === 0 && (
              <div className="text-[10px] text-light-400 italic">Select entities for directional flow analysis</div>
            )}
          </div>
          <div className="flex h-6 rounded-md overflow-hidden mb-1.5">
            {inPct > 0 && (
              <div
                className="flex items-center justify-center transition-all"
                style={{ width: `${inPct}%`, background: 'linear-gradient(90deg, #22c55e, #16a34a)' }}
              >
                {inPct > 15 && (
                  <span className="text-[10px] font-semibold text-white">{formatCurrency(totalInflows)}</span>
                )}
              </div>
            )}
            {outPct > 0 && (
              <div
                className="flex items-center justify-center transition-all"
                style={{ width: `${outPct}%`, background: 'linear-gradient(90deg, #ef4444, #dc2626)' }}
              >
                {outPct > 15 && (
                  <span className="text-[10px] font-semibold text-white">{formatCurrency(totalOutflows)}</span>
                )}
              </div>
            )}
          </div>
          <div className="flex justify-between text-[10px]">
            <span className="text-green-600">▲ Inflows ({inPct.toFixed(0)}%)</span>
            <span className="font-semibold text-light-500">
              Net: <span style={{ color: netFlow >= 0 ? '#16a34a' : '#dc2626' }}>{formatCurrency(netFlow)}</span>
            </span>
            <span className="text-red-600">▼ Outflows ({outPct.toFixed(0)}%)</span>
          </div>
          {/* Entity breakdown — only when entities are selected */}
          {hasEntitySelection && (inflowEntities?.length > 0 || outflowEntities?.length > 0) && (
            <div className="flex gap-4 mt-2 pt-2 border-t border-light-100">
              {/* Inflow entities */}
              <div className="flex-1 min-w-0">
                {inflowEntities?.length > 0 && (
                  <>
                    <div className="text-[9px] text-green-600 font-semibold uppercase tracking-wider mb-1">Inflow From</div>
                    <div className="space-y-0.5">
                      {inflowEntities.slice(0, 5).map((e, i) => (
                        <div key={i} className="flex items-center justify-between text-[10px]">
                          <span className="text-light-600 truncate mr-2">{e.name}</span>
                          <span className="text-green-600 font-medium whitespace-nowrap">{formatCurrency(e.amount)}</span>
                        </div>
                      ))}
                      {inflowEntities.length > 5 && (
                        <div className="text-[9px] text-light-400">+{inflowEntities.length - 5} more</div>
                      )}
                    </div>
                  </>
                )}
              </div>
              {/* Outflow entities */}
              <div className="flex-1 min-w-0">
                {outflowEntities?.length > 0 && (
                  <>
                    <div className="text-[9px] text-red-600 font-semibold uppercase tracking-wider mb-1">Outflow To</div>
                    <div className="space-y-0.5">
                      {outflowEntities.slice(0, 5).map((e, i) => (
                        <div key={i} className="flex items-center justify-between text-[10px]">
                          <span className="text-light-600 truncate mr-2">{e.name}</span>
                          <span className="text-red-600 font-medium whitespace-nowrap">{formatCurrency(e.amount)}</span>
                        </div>
                      ))}
                      {outflowEntities.length > 5 && (
                        <div className="text-[9px] text-light-400">+{outflowEntities.length - 5} more</div>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
