// Force US/Eastern so bare new Date("2024-12-31") (UTC midnight) would shift to Dec 30 locally
process.env.TZ = 'America/New_York'

import { renderHook } from '@testing-library/react'
import { useFilteredEvents } from './use-filtered-events'
import type { TimelineEvent } from '../api'

const makeEvent = (date: string, key = date): TimelineEvent => ({
  key,
  date,
  name: 'test',
  type: 'transaction',
  time: null,
  connections: [],
  summary: null,
  notes: null,
  amount: null,
})

const base = {
  selectedTypes: new Set<string>(),
  selectedEntityKeys: new Set<string>(),
  visibleWindow: null,
  searchTerm: '',
}

describe('useFilteredEvents — date range filter', () => {
  const events = [
    makeEvent('2024-12-29T14:00:00Z', 'dec29'),  // Dec 29 local
    makeEvent('2024-12-30T14:00:00Z', 'dec30'),  // Dec 30 local
    makeEvent('2024-12-31T14:00:00Z', 'dec31'),  // Dec 31 local (9am EST)
    makeEvent('2025-01-01T14:00:00Z', 'jan01'),  // Jan 1 local
  ]

  it('includes all events on the selected end date in a non-UTC timezone', () => {
    const { result } = renderHook(() =>
      useFilteredEvents({
        ...base,
        events,
        dateRange: { start: null, end: '2024-12-31' },
      })
    )
    const keys = result.current.filteredEvents.map((e) => e.key)
    expect(keys).toContain('dec31')
    expect(keys).not.toContain('jan01')
  })

  it('includes all events on the selected start date in a non-UTC timezone', () => {
    const { result } = renderHook(() =>
      useFilteredEvents({
        ...base,
        events,
        dateRange: { start: '2024-12-30', end: null },
      })
    )
    const keys = result.current.filteredEvents.map((e) => e.key)
    expect(keys).toContain('dec30')
    expect(keys).toContain('dec31')
    expect(keys).not.toContain('dec29')
  })

  it('filters to an inclusive range across both bounds', () => {
    const { result } = renderHook(() =>
      useFilteredEvents({
        ...base,
        events,
        dateRange: { start: '2024-12-30', end: '2024-12-31' },
      })
    )
    const keys = result.current.filteredEvents.map((e) => e.key)
    expect(keys).toEqual(['dec30', 'dec31'])
  })
})
