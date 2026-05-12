import { useState, useEffect, useCallback } from 'react'

const API = ''  // proxied to :8000 via vite.config.js

const STRATEGIES = [
  { id: 'vwap_breakout',        label: 'VWAP Breakout',     pts: 20 },
  { id: 'rsi_momentum',         label: 'RSI Momentum',      pts: 15 },
  { id: 'opening_range_breakout', label: 'Opening Range',   pts: 15 },
  { id: 'oi_buildup',           label: 'OI Buildup',        pts: 25 },
]

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}
function monthAgoStr() {
  const d = new Date()
  d.setMonth(d.getMonth() - 1)
  return d.toISOString().slice(0, 10)
}

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-gray-800 rounded-xl p-4 flex flex-col gap-1">
      <span className="text-xs text-gray-400 uppercase tracking-wider">{label}</span>
      <span className={`text-3xl font-bold ${color || 'text-white'}`}>{value}</span>
      {sub && <span className="text-xs text-gray-500">{sub}</span>}
    </div>
  )
}

function OutcomeBadge({ outcome }) {
  const map = {
    TARGET_HIT: 'bg-green-900 text-green-300',
    SL_HIT:     'bg-red-900 text-red-300',
    EXPIRED:    'bg-gray-700 text-gray-400',
    OPEN:       'bg-yellow-900 text-yellow-300',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[outcome] || 'bg-gray-700 text-gray-300'}`}>
      {outcome?.replace('_', ' ')}
    </span>
  )
}

export default function App() {
  const [startDate, setStartDate]     = useState(monthAgoStr())
  const [endDate, setEndDate]         = useState(todayStr())
  const [selected, setSelected]       = useState(new Set())   // selected strategy ids
  const [data, setData]               = useState(null)
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState(null)
  const [sortCol, setSortCol]         = useState('created_at')
  const [sortAsc, setSortAsc]         = useState(false)
  const [symbolFilter, setSymbolFilter] = useState('ALL')
  const [dirFilter, setDirFilter]     = useState('ALL')
  const [outcomeFilter, setOutcomeFilter] = useState('ALL')

  const toggleStrategy = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate })
      if (selected.size > 0) params.set('strategies', [...selected].join(','))
      const res = await fetch(`${API}/api/dashboard?${params}`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      setData(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [startDate, endDate, selected])

  useEffect(() => { fetchData() }, [])

  const signals = data?.signals || []

  // Client-side filters on the signal table
  const filtered = signals.filter(s => {
    if (symbolFilter !== 'ALL' && s.symbol !== symbolFilter) return false
    if (dirFilter !== 'ALL' && s.direction !== dirFilter) return false
    if (outcomeFilter !== 'ALL' && s.outcome !== outcomeFilter) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol]
    if (av == null) av = ''
    if (bv == null) bv = ''
    if (typeof av === 'string') av = av.toLowerCase()
    if (typeof bv === 'string') bv = bv.toLowerCase()
    if (av < bv) return sortAsc ? -1 : 1
    if (av > bv) return sortAsc ? 1 : -1
    return 0
  })

  const handleSort = (col) => {
    if (sortCol === col) setSortAsc(a => !a)
    else { setSortCol(col); setSortAsc(false) }
  }

  const Th = ({ col, children }) => (
    <th
      className="px-3 py-2 text-left text-xs text-gray-400 uppercase cursor-pointer select-none hover:text-white"
      onClick={() => handleSort(col)}
    >
      {children} {sortCol === col ? (sortAsc ? '▲' : '▼') : ''}
    </th>
  )

  const ov = data?.overview

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6 max-w-screen-2xl mx-auto">

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Chanakya Sanket</h1>
        <p className="text-gray-500 text-sm">Trading Intelligence Dashboard</p>
      </div>

      {/* Filters */}
      <div className="bg-gray-900 rounded-xl p-5 mb-6 flex flex-wrap gap-6 items-end">

        {/* Date range */}
        <div className="flex gap-3 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-400">Start date</label>
            <input
              type="date" value={startDate}
              onChange={e => setStartDate(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-400">End date</label>
            <input
              type="date" value={endDate}
              onChange={e => setEndDate(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
            />
          </div>
        </div>

        {/* Strategy toggles */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-400">Strategies (show signals where these fired)</label>
          <div className="flex gap-2 flex-wrap">
            {STRATEGIES.map(s => (
              <button
                key={s.id}
                onClick={() => toggleStrategy(s.id)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border ${
                  selected.has(s.id)
                    ? 'bg-purple-600 border-purple-500 text-white'
                    : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500'
                }`}
              >
                {s.label} <span className="opacity-60 text-xs">+{s.pts}</span>
              </button>
            ))}
            {selected.size > 0 && (
              <button onClick={() => setSelected(new Set())} className="text-xs text-gray-500 hover:text-gray-300 px-2">
                clear
              </button>
            )}
          </div>
        </div>

        <button
          onClick={fetchData}
          disabled={loading}
          className="px-5 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-lg text-sm font-semibold transition-colors"
        >
          {loading ? 'Loading…' : 'Apply'}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg px-4 py-3 mb-6 text-red-300 text-sm">
          {error} — make sure the API server is running on :8000
        </div>
      )}

      {/* Overview cards */}
      {ov && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
          <StatCard label="Signals" value={ov.total_signals} />
          <StatCard label="Win rate" value={`${ov.win_rate}%`}
            color={ov.win_rate >= 40 ? 'text-green-400' : ov.win_rate >= 33 ? 'text-yellow-400' : 'text-red-400'} />
          <StatCard label="Wins" value={ov.wins} color="text-green-400" />
          <StatCard label="Losses" value={ov.losses} color="text-red-400" />
          <StatCard label="Expired" value={ov.expired} color="text-gray-400" />
          <StatCard label="Open" value={ov.open} color="text-yellow-400" />
          <StatCard
            label="Total P&L"
            value={`₹${(ov.total_pnl || 0).toLocaleString('en-IN')}`}
            color={ov.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}
          />
        </div>
      )}

      {/* By Symbol + By Direction */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">By Symbol</h3>
            <div className="space-y-2">
              {data.by_symbol.map(s => (
                <div key={s.symbol} className="flex items-center gap-3">
                  <span className="w-24 text-sm font-medium text-white">{s.symbol}</span>
                  <div className="flex-1 bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div className="h-2 bg-purple-500 rounded-full" style={{ width: `${s.win_rate}%` }} />
                  </div>
                  <span className="text-sm text-gray-300 w-16 text-right">{s.win_rate}% WR</span>
                  <span className="text-xs text-gray-500 w-16 text-right">{s.total} signals</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">By Direction</h3>
            <div className="space-y-2">
              {data.by_direction.map(d => (
                <div key={d.direction} className="flex items-center gap-3">
                  <span className={`w-12 text-sm font-medium ${d.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}`}>
                    {d.direction}
                  </span>
                  <div className="flex-1 bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-2 rounded-full ${d.direction === 'CALL' ? 'bg-green-500' : 'bg-red-500'}`}
                      style={{ width: `${d.win_rate}%` }}
                    />
                  </div>
                  <span className="text-sm text-gray-300 w-16 text-right">{d.win_rate}% WR</span>
                  <span className="text-xs text-gray-500 w-16 text-right">{d.total} signals</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Signal table */}
      {data && (
        <div className="bg-gray-900 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-800 flex flex-wrap gap-3 items-center justify-between">
            <h3 className="font-semibold text-white">
              Signals <span className="text-gray-500 font-normal text-sm">({filtered.length} shown)</span>
            </h3>
            <div className="flex gap-2 flex-wrap">
              {/* Symbol filter */}
              <select value={symbolFilter} onChange={e => setSymbolFilter(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
                <option value="ALL">All symbols</option>
                <option value="NIFTY">NIFTY</option>
                <option value="BANKNIFTY">BANKNIFTY</option>
              </select>
              {/* Direction filter */}
              <select value={dirFilter} onChange={e => setDirFilter(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
                <option value="ALL">All directions</option>
                <option value="CALL">CALL</option>
                <option value="PUT">PUT</option>
              </select>
              {/* Outcome filter */}
              <select value={outcomeFilter} onChange={e => setOutcomeFilter(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
                <option value="ALL">All outcomes</option>
                <option value="TARGET_HIT">Target hit</option>
                <option value="SL_HIT">SL hit</option>
                <option value="EXPIRED">Expired</option>
                <option value="OPEN">Open</option>
              </select>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-800/50">
                <tr>
                  <Th col="created_at">Date/Time</Th>
                  <Th col="symbol">Symbol</Th>
                  <Th col="direction">Dir</Th>
                  <Th col="confidence">Conf</Th>
                  <th className="px-3 py-2 text-left text-xs text-gray-400 uppercase">Strategies</th>
                  <Th col="entry">Entry</Th>
                  <Th col="sl">SL</Th>
                  <Th col="target">Target</Th>
                  <Th col="strike">Strike</Th>
                  <Th col="regime">Regime</Th>
                  <Th col="outcome">Outcome</Th>
                  <Th col="pnl">P&L</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="px-3 py-8 text-center text-gray-500">
                      No signals found for the selected filters
                    </td>
                  </tr>
                ) : sorted.map(s => (
                  <tr key={s.id} className="hover:bg-gray-800/50 transition-colors">
                    <td className="px-3 py-2 text-gray-400 whitespace-nowrap">
                      {s.created_at ? new Date(s.created_at).toLocaleString('en-IN', {
                        month: 'short', day: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                      }) : '—'}
                    </td>
                    <td className="px-3 py-2 font-medium text-white">{s.symbol}</td>
                    <td className="px-3 py-2">
                      <span className={`font-semibold ${s.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}`}>
                        {s.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`font-medium ${s.confidence >= 75 ? 'text-purple-400' : s.confidence >= 60 ? 'text-blue-400' : 'text-gray-400'}`}>
                        {s.confidence}%
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(s.strategies_fired || []).map(strat => (
                          <span key={strat} className="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded">
                            {strat.replace('_breakout', '').replace('_momentum', '').replace('opening_range', 'ORB').replace('oi_buildup', 'OI')}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-gray-300">{s.entry?.toFixed(0)}</td>
                    <td className="px-3 py-2 text-red-400">{s.sl?.toFixed(0)}</td>
                    <td className="px-3 py-2 text-green-400">{s.target?.toFixed(0)}</td>
                    <td className="px-3 py-2 text-gray-400">{s.strike}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{s.regime}</td>
                    <td className="px-3 py-2"><OutcomeBadge outcome={s.outcome} /></td>
                    <td className="px-3 py-2">
                      {s.pnl != null ? (
                        <span className={s.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                          ₹{s.pnl.toLocaleString('en-IN')}
                        </span>
                      ) : <span className="text-gray-600">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
