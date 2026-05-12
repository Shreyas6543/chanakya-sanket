import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import type { Signal } from '../types'

interface Props {
  signals: Signal[]
}

interface MonthPoint {
  month:    string   // "Nov '25"
  winRate:  number
  wins:     number
  losses:   number
  expired:  number
  total:    number
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function MonthlyBreakdown({ signals }: Props) {
  const resolved = signals.filter(
    s => s.signal_time != null && ['TARGET_HIT', 'SL_HIT', 'EXPIRED', 'USER_CLOSED'].includes(s.outcome)
  )

  if (resolved.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-4 flex items-center justify-center h-48">
        <p className="text-xs text-gray-600">No resolved signals yet</p>
      </div>
    )
  }

  // Group by YYYY-MM
  const map = new Map<string, { wins: number; losses: number; expired: number }>()
  for (const s of resolved) {
    const key = s.signal_time!.slice(0, 7) // "2025-11"
    const r = map.get(key) ?? { wins: 0, losses: 0, expired: 0 }
    if (s.outcome === 'TARGET_HIT') r.wins++
    else if (s.outcome === 'SL_HIT') r.losses++
    else r.expired++
    map.set(key, r)
  }

  const points: MonthPoint[] = [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, r]) => {
      const [year, mo] = key.split('-')
      const total = r.wins + r.losses + r.expired
      return {
        month:   `${MONTH_NAMES[parseInt(mo) - 1]} '${year.slice(2)}`,
        winRate: total > 0 ? Math.round(r.wins / total * 100) : 0,
        wins:    r.wins,
        losses:  r.losses,
        expired: r.expired,
        total,
      }
    })

  const barColor = (wr: number) =>
    wr >= 40 ? '#22c55e' : wr >= 33 ? '#eab308' : '#ef4444'

  return (
    <div className="bg-gray-900 rounded-xl p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-gray-400">Monthly Win Rate</h3>
        <p className="text-xs text-gray-600">Resolved signals only · green ≥40% · yellow ≥33% break-even · red below</p>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={points} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fill: '#6b7280', fontSize: 10 }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: '#6b7280', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `${v}%`}
          />
          <ReferenceLine y={33} stroke="#374151" strokeDasharray="4 2" label={{ value: 'BE', position: 'right', fill: '#4b5563', fontSize: 9 }} />
          <Tooltip
            contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 }}
            labelStyle={{ color: '#9ca3af', fontSize: 11 }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              const d = payload[0].payload as MonthPoint
              return (
                <div style={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8, padding: '8px 12px' }}>
                  <p style={{ color: '#9ca3af', fontSize: 11, marginBottom: 4 }}>{label}</p>
                  <p style={{ color: barColor(d.winRate), fontWeight: 600, fontSize: 14 }}>{d.winRate}% WR</p>
                  <p style={{ color: '#6b7280', fontSize: 11 }}>{d.wins}W · {d.losses}L · {d.expired}E · {d.total} total</p>
                </div>
              )
            }}
          />
          <Bar dataKey="winRate" radius={[3, 3, 0, 0]} maxBarSize={40}>
            {points.map((p, i) => (
              <Cell key={i} fill={barColor(p.winRate)} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
