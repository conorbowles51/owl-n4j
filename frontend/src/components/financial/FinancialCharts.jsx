import { useState, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { ChevronDown, ChevronRight, BarChart3 } from 'lucide-react';
import { CATEGORY_COLORS } from './constants';

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
    const category = item.category || 'Uncategorized';
    groups[key][category] = (groups[key][category] || 0) + (item.total_amount || 0);
  });

  return Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([period, categories]) => ({ period, ...categories }));
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

export default function FinancialCharts({ volumeData = [], transactions = [], categoryColorMap = {} }) {
  const [isExpanded, setIsExpanded] = useState(true);

  const dates = useMemo(() => volumeData.map(d => d.date).filter(Boolean), [volumeData]);
  const grouping = useMemo(() => detectGrouping(dates), [dates]);
  const barData = useMemo(() => groupByPeriod(volumeData, grouping), [volumeData, grouping]);

  const allCategories = useMemo(() => {
    const cats = new Set();
    volumeData.forEach(d => cats.add(d.category || 'Uncategorized'));
    return [...cats];
  }, [volumeData]);

  const categoryData = useMemo(() => {
    const counts = {};
    transactions.forEach(t => {
      const cat = t.financial_category || 'Uncategorized';
      counts[cat] = (counts[cat] || 0) + 1;
    });
    return Object.entries(counts).map(([name, value]) => ({
      name,
      value,
      color: categoryColorMap[name] || CATEGORY_COLORS[name] || '#9ca3af',
    }));
  }, [transactions, categoryColorMap]);

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
                  {allCategories.map(cat => (
                    <Bar
                      key={cat}
                      dataKey={cat}
                      stackId="volume"
                      fill={categoryColorMap[cat] || CATEGORY_COLORS[cat] || '#9ca3af'}
                      name={cat}
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
