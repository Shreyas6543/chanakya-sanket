import { useState, useEffect, useCallback } from 'react'
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend, Area,
} from 'recharts'

interface OIRow {
  date:     string
  call_oi:  number
  put_oi:   number
  total_oi: number
  pcr:      number | null
  spot:     number
}

function todayStr() { return new Date().toISOString().slice(0, 10) }

function fmtOI(v: number) {
  if (v >= 1_00_00_000) return `${(v / 1_00_00_000).toFixed(1)}Cr`
  if (v >= 1_00_000)    return `${(v / 1_00_000).toFixed(1)}L`
  return v.toLocaleString('en-IN')
}

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

// Tick every N dates so labels don't crowd
function tickFormatter(value: string, _: number, data: OIRow[], step: number) {
  const idx = data.findIndex(r => r.date === value)
  return idx >= 0 && idx % step === 0 ? fmtDate(value) : ''
}

export default function OIPage() {
  const [symbol, setSymbol]     = useState('NIFTY')
  const [startDate, setStart]   = useState('2024-01-01')
  const [endDate, setEnd]       = useState(todayStr)
  const [data, setData]         = useState<OIRow[]>([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true); setError(null)
    fetch(`/api/oi-history?symbol=${symbol}&start_date=${startDate}&end_date=${endDate}`)
      .then(r => r.json())
      .then((d: OIRow[]) => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [symbol, startDate, endDate])

  useEffect(() => { load() }, [load])

  const n    = data.length
  const step = Math.max(1, Math.ceil(n / 12))

  // PCR stats
  const pcrs    = data.filter(r => r.pcr != null).map(r => r.pcr!)
  const avgPcr  = pcrs.length ? pcrs.reduce((a, b) => a + b, 0) / pcrs.length : null
  const maxPcr  = pcrs.length ? Math.max(...pcrs) : null
  const minPcr  = pcrs.length ? Math.min(...pcrs) : null

  const latestPcr  = n > 0 ? data[n - 1].pcr : null
  const pcrSentiment = latestPcr == null ? '—'
    : latestPcr > 1.2 ? 'Bearish (Puts dominate)'
    : latestPcr < 0.7 ? 'Bullish (Calls dominate)'
    : 'Neutral'

  const tooltipStyle = {
    contentStyle: { backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 },
    labelStyle:   { color: '#9ca3af', fontSize: 11 },
    itemStyle:    { fontSize: 11 },
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6 max-w-screen-2xl mx-auto">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Open Interest &amp; PCR</h2>
          <p className="text-gray-500 text-sm">NSE F&amp;O Bhavcopy · Daily aggregates</p>
        </div>

        <div className="flex gap-3 items-center flex-wrap">
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
          >
            <option value="NIFTY">NIFTY</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
          </select>
          <input type="date" value={startDate} onChange={e => setStart(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500" />
          <input type="date" value={endDate} onChange={e => setEnd(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500" />
          <button onClick={load}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition-colors">
            Load
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg px-4 py-3 mb-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-48 text-gray-500">
          <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mr-3" />
          Loading OI data… (may take a few seconds for large ranges)
        </div>
      )}

      {!loading && n > 0 && (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            {[
              { label: 'Days',        value: n,                                    color: 'text-white' },
              { label: 'Latest PCR',  value: latestPcr?.toFixed(3) ?? '—',        color: latestPcr != null && latestPcr > 1 ? 'text-red-400' : 'text-green-400' },
              { label: 'Avg PCR',     value: avgPcr?.toFixed(3) ?? '—',           color: 'text-gray-300' },
              { label: 'Sentiment',   value: pcrSentiment,                         color: 'text-yellow-400' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-gray-900 rounded-xl p-4">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">{label}</div>
                <div className={`text-lg font-bold truncate ${color}`}>{value}</div>
              </div>
            ))}
          </div>

          {/* ── Chart 1: Call OI vs Put OI ── */}
          <div className="bg-gray-900 rounded-xl p-4 mb-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-1">Call OI vs Put OI</h3>
            <p className="text-xs text-gray-600 mb-4">Total open interest across all strikes &amp; expiries · {symbol}</p>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data} margin={{ top: 4, right: 12, left: 16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tickFormatter={v => tickFormatter(v, 0, data, step)}
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={fmtOI}
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickLine={false} axisLine={false}
                />
                <Tooltip
                  {...tooltipStyle}
                  labelFormatter={(d: unknown) => fmtDate(String(d))}
                  formatter={(v: unknown, name: unknown) => [fmtOI(v as number), String(name)]}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
                <Area type="monotone" dataKey="call_oi" name="Call OI" stroke="#22c55e"
                  fill="#16a34a" fillOpacity={0.15} strokeWidth={1.5} dot={false} />
                <Area type="monotone" dataKey="put_oi" name="Put OI" stroke="#ef4444"
                  fill="#dc2626" fillOpacity={0.15} strokeWidth={1.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* ── Chart 2: PCR + Spot ── */}
          <div className="bg-gray-900 rounded-xl p-4 mb-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-1">Put-Call Ratio (PCR)</h3>
            <p className="text-xs text-gray-600 mb-1">
              PCR &gt; 1.2 → bearish (put buyers dominate) · PCR &lt; 0.7 → bullish (call buyers dominate)
            </p>
            <div className="flex gap-4 text-xs text-gray-600 mb-4">
              <span>Min: <span className="text-green-400">{minPcr?.toFixed(3)}</span></span>
              <span>Max: <span className="text-red-400">{maxPcr?.toFixed(3)}</span></span>
              <span>Avg: <span className="text-gray-300">{avgPcr?.toFixed(3)}</span></span>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={data} margin={{ top: 4, right: 12, left: 16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tickFormatter={v => tickFormatter(v, 0, data, step)}
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="pcr"
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickLine={false} axisLine={false}
                  domain={['auto', 'auto']}
                  tickFormatter={v => v.toFixed(2)}
                />
                <Tooltip
                  {...tooltipStyle}
                  labelFormatter={(d: unknown) => fmtDate(String(d))}
                  formatter={(v: unknown, name: unknown) =>
                    name === 'PCR' ? [(v as number).toFixed(3), String(name)] : [fmtOI(v as number), String(name)]
                  }
                />
                <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
                {/* Neutral band */}
                <ReferenceLine yAxisId="pcr" y={1.2} stroke="#ef4444" strokeDasharray="4 3" strokeWidth={1} label={{ value: 'Bearish 1.2', fill: '#6b7280', fontSize: 9, position: 'insideTopRight' }} />
                <ReferenceLine yAxisId="pcr" y={1.0} stroke="#6b7280" strokeDasharray="4 3" strokeWidth={1} label={{ value: 'Neutral 1.0', fill: '#6b7280', fontSize: 9, position: 'insideTopRight' }} />
                <ReferenceLine yAxisId="pcr" y={0.7} stroke="#22c55e" strokeDasharray="4 3" strokeWidth={1} label={{ value: 'Bullish 0.7', fill: '#6b7280', fontSize: 9, position: 'insideTopRight' }} />
                <Area
                  yAxisId="pcr"
                  type="monotone" dataKey="pcr" name="PCR"
                  stroke="#a855f7" fill="#7c3aed" fillOpacity={0.15}
                  strokeWidth={2} dot={false} connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* ── Chart 3: Spot Price + Total OI ── */}
          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-1">Spot Price &amp; Total OI</h3>
            <p className="text-xs text-gray-600 mb-4">Rising price + rising OI = long buildup (bullish) · Rising price + falling OI = short covering</p>
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={data} margin={{ top: 4, right: 12, left: 16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="date"
                  tickFormatter={v => tickFormatter(v, 0, data, step)}
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="spot"
                  orientation="right"
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickLine={false} axisLine={false}
                  domain={['auto', 'auto']}
                  tickFormatter={v => v.toFixed(0)}
                />
                <YAxis
                  yAxisId="oi"
                  orientation="left"
                  tickFormatter={fmtOI}
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickLine={false} axisLine={false}
                />
                <Tooltip
                  {...tooltipStyle}
                  labelFormatter={(d: unknown) => fmtDate(String(d))}
                  formatter={(v: unknown, name: unknown) =>
                    name === 'Spot' ? [(v as number).toFixed(2), String(name)] : [fmtOI(v as number), String(name)]
                  }
                />
                <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
                <Bar yAxisId="oi" dataKey="total_oi" name="Total OI" fill="#3b82f6" opacity={0.35} />
                <Line yAxisId="spot" type="monotone" dataKey="spot" name="Spot"
                  stroke="#f59e0b" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {!loading && n === 0 && !error && (
        <div className="bg-gray-900 rounded-xl p-12 text-center text-gray-500">
          No OI data for {symbol} in selected range. Data starts Jan 2024.
        </div>
      )}
    </div>
  )
}
