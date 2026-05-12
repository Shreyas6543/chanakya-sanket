import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { Signal } from '../types'

interface Props {
  signals: Signal[]
}

interface CurvePoint {
  date:       string   // display label
  cumPnl:     number   // running total
  drawdown:   number   // from peak (always ≤ 0)
  signalId:   number
  outcome:    string
}

export default function EquityCurve({ signals }: Props) {
  // Only resolved signals with P&L
  const resolved = signals
    .filter(s => s.pnl != null && s.signal_time != null)
    .sort((a, b) => (a.signal_time! < b.signal_time! ? -1 : 1))

  if (resolved.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-4 flex items-center justify-center h-48">
        <p className="text-xs text-gray-600">No resolved signals with P&L yet</p>
      </div>
    )
  }

  let cumPnl = 0
  let peak   = 0
  const points: CurvePoint[] = resolved.map(s => {
    cumPnl += s.pnl!
    if (cumPnl > peak) peak = cumPnl
    return {
      date:     new Date(s.signal_time!).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }),
      cumPnl:   Math.round(cumPnl),
      drawdown: Math.round(cumPnl - peak),
      signalId: s.id,
      outcome:  s.outcome,
    }
  })

  const finalPnl    = points[points.length - 1].cumPnl
  const minDrawdown = Math.min(...points.map(p => p.drawdown))
  const maxPnl      = Math.max(...points.map(p => p.cumPnl))

  const areaColor  = finalPnl >= 0 ? '#22c55e' : '#ef4444'
  const areaFill   = finalPnl >= 0 ? '#16a34a' : '#dc2626'

  const formatPnl = (v: number) =>
    `₹${Math.abs(v).toLocaleString('en-IN')}${v < 0 ? ' loss' : ''}`

  return (
    <div className="bg-gray-900 rounded-xl p-4">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-400">Equity Curve</h3>
          <p className="text-xs text-gray-600">Cumulative P&L across {resolved.length} resolved signals</p>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold ${finalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {finalPnl >= 0 ? '+' : ''}₹{Math.abs(finalPnl).toLocaleString('en-IN')}
          </div>
          <div className="text-xs text-gray-500">
            Peak ₹{maxPnl.toLocaleString('en-IN')} · Max DD {formatPnl(minDrawdown)}
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={points} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={areaFill} stopOpacity={0.3} />
              <stop offset="95%" stopColor={areaFill} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="date"
            tick={{ fill: '#6b7280', fontSize: 10 }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#6b7280', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`}
          />
          <ReferenceLine y={0} stroke="#374151" strokeDasharray="4 2" />
          <Tooltip
            contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 }}
            labelStyle={{ color: '#9ca3af', fontSize: 11 }}
            formatter={(value: unknown) => [
              `₹${Number(value).toLocaleString('en-IN')}`,
              'Cumulative P&L',
            ]}
          />
          <Area
            type="monotone"
            dataKey="cumPnl"
            stroke={areaColor}
            strokeWidth={2}
            fill="url(#pnlGrad)"
            dot={false}
            activeDot={{ r: 4, fill: areaColor }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
