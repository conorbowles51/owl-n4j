import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
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

export default function FinancialCharts({ volumeData = [], categoryBreakdown = {}, categoryColorMap = {} }) {
  const dates = useMemo(() => volumeData.map(d => d.date).filter(Boolean), [volumeData]);
  const grouping = useMemo(() => detectGrouping(dates), [dates]);
  const barData = useMemo(() => groupByPeriod(volumeData, grouping), [volumeData, grouping]);

  const allCategories = useMemo(() => {
    const cats = new Set();
    volumeData.forEach(d => cats.add(d.category || 'Uncategorized'));
    return [...cats];
  }, [volumeData]);

  // Build donut chart data from server-provided category breakdown
  const categoryData = useMemo(() => {
    return Object.entries(categoryBreakdown).map(([name, data]) => ({
      name,
      value: data.count,
      color: categoryColorMap[name] || CATEGORY_COLORS[name] || '#9ca3af',
    }));
  }, [categoryBreakdown, categoryColorMap]);

  const hasCategoryData = Object.keys(categoryBreakdown).length > 0;
  if (volumeData.length === 0 && !hasCategoryData) return null;

  return (
    <div className="border border-light-200 rounded-lg bg-white p-2">
      <div className="flex gap-3">
        {/* Stacked Bar Chart - Volume over time (60%) */}
        <div className="w-[60%] min-w-0">
          <div className="text-xs text-light-600 mb-2 font-medium">
            Volume Over Time ({grouping === 'month' ? 'Monthly' : grouping === 'week' ? 'Weekly' : 'Daily'})
          </div>
          {barData.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
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
            <div className="flex items-center justify-center h-[140px] text-xs text-light-500">No volume data</div>
          )}
        </div>

        {/* Donut Chart - Category distribution (40%) */}
        <div className="w-[40%] min-w-0">
          <div className="text-xs text-light-600 mb-2 font-medium">Category Distribution</div>
          {categoryData.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
              <PieChart>
                <Pie
                  data={categoryData}
                  cx="50%"
                  cy="50%"
                  innerRadius={30}
                  outerRadius={50}
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
            <div className="flex items-center justify-center h-[140px] text-xs text-light-500">No category data</div>
          )}
        </div>
      </div>
    </div>
  );
}
