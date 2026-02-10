import { useState, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { ChevronDown, ChevronRight, BarChart3 } from 'lucide-react';

const TYPE_COLORS = {
  Transaction: '#06b6d4',
  Transfer: '#14b8a6',
  Payment: '#84cc16',
  Invoice: '#f97316',
  Deposit: '#3b82f6',
  Withdrawal: '#ef4444',
  Other: '#6b7280',
};

const CATEGORY_COLORS = {
  Suspicious: '#ef4444',
  Legitimate: '#22c55e',
  'Under Review': '#f59e0b',
  Unknown: '#6b7280',
};

function detectGrouping(dates) {
  if (dates.length < 2) return 'day';
  const sorted = [...dates].sort();
  const first = new Date(sorted[0]);
  const last = new Date(sorted[sorted.length - 1]);
  const spanDays = (last - first) / (1000 * 60 * 60 * 24);
  if (spanDays > 365) return 'month';
  if (spanDays > 60) return 'month';
  if (spanDays > 14) return 'week';
  return 'day';
}

function groupByPeriod(data, grouping) {
  const groups = {};

  data.forEach(item => {
    if (!item.date) return;
    let key;
    const d = new Date(item.date);
    if (grouping === 'month') {
      key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    } else if (grouping === 'week') {
      const dayOfWeek = d.getDay();
      const weekStart = new Date(d);
      weekStart.setDate(d.getDate() - dayOfWeek);
      key = weekStart.toISOString().slice(0, 10);
    } else {
      key = item.date;
    }

    if (!groups[key]) groups[key] = {};
    const type = item.type || 'Other';
    groups[key][type] = (groups[key][type] || 0) + (item.total_amount || 0);
  });

  return Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([period, types]) => ({ period, ...types }));
}

function formatPeriodLabel(period, grouping) {
  if (grouping === 'month') {
    const [y, m] = period.split('-');
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[parseInt(m) - 1]} ${y.slice(2)}`;
  }
  if (grouping === 'week') {
    const d = new Date(period);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  }
  const d = new Date(period);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export default function FinancialCharts({ volumeData = [], transactions = [] }) {
  const [isExpanded, setIsExpanded] = useState(true);

  const dates = useMemo(() => volumeData.map(d => d.date).filter(Boolean), [volumeData]);
  const grouping = useMemo(() => detectGrouping(dates), [dates]);
  const barData = useMemo(() => groupByPeriod(volumeData, grouping), [volumeData, grouping]);

  const allTypes = useMemo(() => {
    const types = new Set();
    volumeData.forEach(d => types.add(d.type || 'Other'));
    return [...types];
  }, [volumeData]);

  const categoryData = useMemo(() => {
    const counts = {};
    transactions.forEach(t => {
      const cat = t.financial_category || 'Unknown';
      counts[cat] = (counts[cat] || 0) + 1;
    });
    return Object.entries(counts).map(([name, value]) => ({
      name,
      value,
      color: CATEGORY_COLORS[name] || '#6b7280',
    }));
  }, [transactions]);

  if (volumeData.length === 0 && transactions.length === 0) return null;

  return (
    <div className="border border-light-200 rounded-lg bg-white">
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-light-50 select-none"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown className="w-4 h-4 text-light-500" /> : <ChevronRight className="w-4 h-4 text-light-500" />}
        <BarChart3 className="w-4 h-4 text-light-600" />
        <span className="text-sm font-medium text-light-700">Charts</span>
      </div>

      {isExpanded && (
        <div className="px-3 pb-3 space-y-4">
          {/* Stacked Bar Chart - Volume over time */}
          <div>
            <div className="text-xs text-light-600 mb-2 font-medium">
              Volume Over Time ({grouping === 'month' ? 'Monthly' : grouping === 'week' ? 'Weekly' : 'Daily'})
            </div>
            {barData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={barData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis
                    dataKey="period"
                    tickFormatter={(v) => formatPeriodLabel(v, grouping)}
                    tick={{ fontSize: 10 }}
                  />
                  <YAxis
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}K` : v}
                  />
                  <Tooltip
                    formatter={(value) => [`$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, undefined]}
                    labelFormatter={(label) => formatPeriodLabel(label, grouping)}
                  />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  {allTypes.map(type => (
                    <Bar
                      key={type}
                      dataKey={type}
                      stackId="volume"
                      fill={TYPE_COLORS[type] || TYPE_COLORS.Other}
                      name={type}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[220px] text-xs text-light-500">No volume data</div>
            )}
          </div>

          {/* Donut Chart - Category distribution */}
          <div>
            <div className="text-xs text-light-600 mb-2 font-medium">Category Distribution</div>
            {categoryData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={categoryData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    dataKey="value"
                    nameKey="name"
                    paddingAngle={2}
                  >
                    {categoryData.map((entry, idx) => (
                      <Cell key={idx} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value, name) => [value, name]} />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[220px] text-xs text-light-500">No category data</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
