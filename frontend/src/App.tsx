import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import ClaudePanel from './components/ClaudePanel'
import EquityCurve from './components/EquityCurve'
import MonthlyBreakdown from './components/MonthlyBreakdown'
import LivePrices from './components/LivePrices'
import type {
  DashboardData, Signal, SignalState, Source,
  SymbolFilter, DirFilter, OutcomeFilter, SourceFilter, ByHour, ByCombo,
} from './types'

const STRATEGIES = [
  { id: 'vwap_breakout',          label: 'VWAP Breakout', pts: 20 },
  { id: 'rsi_momentum',           label: 'RSI Momentum',  pts: 15 },
  { id: 'opening_range_breakout', label: 'Opening Range', pts: 15 },
  { id: 'oi_buildup',             label: 'OI Buildup',    pts: 25 },
] as const

const STRAT_ABBR: Record<string, string> = {
  vwap_breakout:          'VWAP',
  rsi_momentum:           'RSI',
  opening_range_breakout: 'ORB',
  oi_buildup:             'OI',
}
const abbr = (s: string) => STRAT_ABBR[s] ?? s

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

// ── Shared components ─────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: string | number
  sub?:  string
  color?: string
}
function StatCard({ label, value, sub, color }: StatCardProps) {
  return (
    <div className="bg-gray-800 rounded-xl p-4 flex flex-col gap-1">
      <span className="text-xs text-gray-400 uppercase tracking-wider">{label}</span>
      <span className={`text-3xl font-bold ${color ?? 'text-white'}`}>{value}</span>
      {sub && <span className="text-xs text-gray-500">{sub}</span>}
    </div>
  )
}

const OUTCOME_STYLE: Record<SignalState, string> = {
  TARGET_HIT:  'bg-green-900 text-green-300',
  SL_HIT:      'bg-red-900 text-red-300',
  EXPIRED:     'bg-gray-700 text-gray-400',
  OPEN:        'bg-yellow-900 text-yellow-300',
  USER_CLOSED: 'bg-blue-900 text-blue-300',
}
const OUTCOME_LABEL: Record<SignalState, string> = {
  TARGET_HIT:  'Target Hit',
  SL_HIT:      'SL Hit',
  EXPIRED:     'Expired',
  OPEN:        'Open',
  USER_CLOSED: 'Sold',
}
function OutcomeBadge({ outcome }: { outcome: SignalState }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${OUTCOME_STYLE[outcome] ?? 'bg-gray-700 text-gray-300'}`}>
      {OUTCOME_LABEL[outcome] ?? outcome.replace(/_/g, ' ')}
    </span>
  )
}

function SourceBadge({ source }: { source: Source }) {
  const style: Record<Source, string> = {
    live:       'bg-emerald-900 text-emerald-300',
    historical: 'bg-gray-700 text-gray-400',
    mock:       'bg-orange-900 text-orange-300',
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs ${style[source]}`}>{source}</span>
  )
}

interface WRBarProps { label: string; winRate: number; wins: number; total: number; labelWidth?: string }
function WRBar({ label, winRate, wins, total, labelWidth = 'w-28' }: WRBarProps) {
  const barColor = winRate >= 40 ? 'bg-green-500' : winRate >= 33 ? 'bg-yellow-500' : 'bg-red-500'
  const textColor = winRate >= 40 ? 'text-green-400' : winRate >= 33 ? 'text-yellow-400' : 'text-red-400'
  return (
    <div className="flex items-center gap-3">
      <span className={`${labelWidth} text-xs text-gray-300 truncate shrink-0`} title={label}>{label}</span>
      <div className="flex-1 bg-gray-800 rounded-full h-2 overflow-hidden">
        <div className={`h-2 rounded-full ${barColor}`} style={{ width: `${winRate}%` }} />
      </div>
      <span className={`text-sm font-medium w-10 text-right shrink-0 ${textColor}`}>{winRate}%</span>
      <span className="text-xs text-gray-600 w-16 text-right shrink-0">{wins}/{total}</span>
    </div>
  )
}

// ── Main app ──────────────────────────────────────────────────────────────────

type SortKey = keyof Signal

export default function App() {
  const [startDate, setStartDate]       = useState('2024-05-13')
  const [endDate, setEndDate]           = useState(todayStr)
  const [selected, setSelected]         = useState<Set<string>>(new Set())
  const [data, setData]                 = useState<DashboardData | null>(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState<string | null>(null)

  // Table controls
  const [sortCol, setSortCol]           = useState<SortKey>('signal_time')
  const [sortAsc, setSortAsc]           = useState(false)
  const [symbolFilter, setSymbolFilter] = useState<SymbolFilter>('ALL')
  const [dirFilter, setDirFilter]       = useState<DirFilter>('ALL')
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>('ALL')
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('ALL')

  const toggleStrategy = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate })
      if (selected.size > 0) params.set('strategies', [...selected].join(','))
      const res = await fetch(`/api/dashboard?${params}`)
      if (!res.ok) throw new Error(`API error ${res.status}`)
      setData(await res.json() as DashboardData)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [startDate, endDate, selected])

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => { void fetchData() }, 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [fetchData])

  const signals = data?.signals ?? []

  // Client-side filters
  const filtered = useMemo(() => signals.filter(s => {
    if (symbolFilter  !== 'ALL' && s.symbol    !== symbolFilter)  return false
    if (dirFilter     !== 'ALL' && s.direction !== dirFilter)     return false
    if (outcomeFilter !== 'ALL' && s.outcome   !== outcomeFilter) return false
    if (sourceFilter  !== 'ALL' && s.source    !== sourceFilter)  return false
    return true
  }), [signals, symbolFilter, dirFilter, outcomeFilter, sourceFilter])

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    let av: unknown = a[sortCol]
    let bv: unknown = b[sortCol]
    if (av == null) av = ''
    if (bv == null) bv = ''
    const as = typeof av === 'string' ? av.toLowerCase() : (av as number)
    const bs = typeof bv === 'string' ? bv.toLowerCase() : (bv as number)
    if (as < bs) return sortAsc ? -1 : 1
    if (as > bs) return sortAsc ? 1 : -1
    return 0
  }), [filtered, sortCol, sortAsc])

  const handleSort = (col: SortKey) => {
    if (sortCol === col) setSortAsc(a => !a)
    else { setSortCol(col); setSortAsc(false) }
  }

  const Th = ({ col, children }: { col: SortKey; children: React.ReactNode }) => (
    <th
      className="px-3 py-2 text-left text-xs text-gray-400 uppercase cursor-pointer select-none hover:text-white"
      onClick={() => handleSort(col)}
    >
      {children} {sortCol === col ? (sortAsc ? '▲' : '▼') : ''}
    </th>
  )

  // Client-side by_hour + by_combo (respect filters)
  const byHour = useMemo((): ByHour[] => {
    const map = new Map<number, { wins: number; total: number }>()
    for (const s of signals) {
      if (s.hour == null) continue
      const r = map.get(s.hour) ?? { wins: 0, total: 0 }
      r.total++
      if (s.outcome === 'TARGET_HIT') r.wins++
      map.set(s.hour, r)
    }
    return [...map.entries()]
      .map(([hour, r]) => ({ hour, ...r, win_rate: Math.round(r.wins / r.total * 100) }))
      .sort((a, b) => a.hour - b.hour)
  }, [signals])

  const byCombo = useMemo((): ByCombo[] => {
    const map = new Map<string, { wins: number; total: number }>()
    for (const s of signals) {
      if (!s.strategies_fired?.length) continue
      const key = [...s.strategies_fired].sort().join('+')
      const r = map.get(key) ?? { wins: 0, total: 0 }
      r.total++
      if (s.outcome === 'TARGET_HIT') r.wins++
      map.set(key, r)
    }
    return [...map.entries()]
      .map(([combo, r]) => ({ combo, ...r, win_rate: Math.round(r.wins / r.total * 100) }))
      .filter(r => r.total >= 3)
      .sort((a, b) => b.total - a.total)
  }, [signals])

  const ov = data?.overview

  const wrColor = (wr: number) =>
    wr >= 40 ? 'text-green-400' : wr >= 33 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6 max-w-screen-2xl mx-auto">

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Chanakya Sanket</h1>
          <p className="text-gray-500 text-sm">Trading Intelligence Dashboard</p>
        </div>
        <div className="flex-1 min-w-0 max-w-xl">
          <LivePrices />
        </div>
      </div>

      {/* Filters */}
      <div className="bg-gray-900 rounded-xl p-5 mb-6 flex flex-wrap gap-6 items-end">
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

        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-400">Strategies (signals where these fired)</label>
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

        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            Loading…
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg px-4 py-3 mb-6 text-red-300 text-sm">
          {error} — make sure the API server is running on :8000
        </div>
      )}

      {/* Overview stat cards */}
      {ov && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
          <StatCard label="Signals"   value={ov.total_signals} />
          <StatCard label="Win rate"  value={`${ov.win_rate}%`} color={wrColor(ov.win_rate)} />
          <StatCard label="Wins"      value={ov.wins}    color="text-green-400" />
          <StatCard label="Losses"    value={ov.losses}  color="text-red-400" />
          <StatCard label="Expired"   value={ov.expired} color="text-gray-400" sub="incl. sold" />
          <StatCard label="Open"      value={ov.open}    color="text-yellow-400" />
          <StatCard
            label="Total P&L"
            value={`₹${(ov.total_pnl ?? 0).toLocaleString('en-IN')}`}
            color={(ov.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}
          />
        </div>
      )}

      {/* Equity Curve + Monthly Breakdown */}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <EquityCurve signals={signals} />
          <MonthlyBreakdown signals={signals} />
        </div>
      )}

      {/* By Symbol + By Direction */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">By Symbol</h3>
            <div className="space-y-2">
              {data.by_symbol.map(s => (
                <WRBar
                  key={s.symbol}
                  label={s.symbol}
                  winRate={s.win_rate}
                  wins={s.wins}
                  total={s.total}
                  labelWidth="w-24"
                />
              ))}
            </div>
          </div>
          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">By Direction</h3>
            <div className="space-y-2">
              {data.by_direction.map(d => (
                <div key={d.direction} className="flex items-center gap-3">
                  <span className={`w-12 text-sm font-medium shrink-0 ${d.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}`}>
                    {d.direction}
                  </span>
                  <div className="flex-1 bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-2 rounded-full ${d.direction === 'CALL' ? 'bg-green-500' : 'bg-red-500'}`}
                      style={{ width: `${d.win_rate}%` }}
                    />
                  </div>
                  <span className="text-sm text-gray-300 w-10 text-right shrink-0">{d.win_rate}%</span>
                  <span className="text-xs text-gray-500 w-16 text-right shrink-0">{d.wins}/{d.total}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* By Hour + By Strategy Combo */}
      {data && (byHour.length > 0 || byCombo.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-1">Win Rate by Hour</h3>
            <p className="text-xs text-gray-600 mb-3">Which time window generates the best signals</p>
            {byHour.length === 0
              ? <p className="text-xs text-gray-600">No hour data yet</p>
              : (
                <div className="space-y-2">
                  {byHour.map(r => (
                    <WRBar
                      key={r.hour}
                      label={`${String(r.hour).padStart(2, '0')}:00`}
                      winRate={r.win_rate}
                      wins={r.wins}
                      total={r.total}
                      labelWidth="w-12"
                    />
                  ))}
                  <p className="text-xs text-gray-700 pt-1">Green ≥40% · Yellow ≥33% (break-even) · Red below</p>
                </div>
              )}
          </div>

          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-1">Win Rate by Strategy Combo</h3>
            <p className="text-xs text-gray-600 mb-3">Which combinations actually win (min 3 signals)</p>
            {byCombo.length === 0
              ? <p className="text-xs text-gray-600">Not enough data yet</p>
              : (
                <div className="space-y-2">
                  {byCombo.map(r => (
                    <WRBar
                      key={r.combo}
                      label={r.combo.split('+').map(abbr).join(' + ')}
                      winRate={r.win_rate}
                      wins={r.wins}
                      total={r.total}
                    />
                  ))}
                  <p className="text-xs text-gray-700 pt-1">Green ≥40% · Yellow ≥33% (break-even) · Red below</p>
                </div>
              )}
          </div>
        </div>
      )}

      {/* Claude AI Analyst */}
      <div className="mb-6">
        <ClaudePanel dashboardData={data} />
      </div>

      {/* Signal table */}
      {data && (
        <div className="bg-gray-900 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-800 flex flex-wrap gap-3 items-center justify-between">
            <h3 className="font-semibold text-white">
              Signals <span className="text-gray-500 font-normal text-sm">({filtered.length} shown)</span>
            </h3>
            <div className="flex gap-2 flex-wrap">
              <select value={sourceFilter} onChange={e => setSourceFilter(e.target.value as SourceFilter)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
                <option value="ALL">All sources</option>
                <option value="live">Live only</option>
                <option value="historical">Historical</option>
                <option value="mock">Mock</option>
              </select>
              <select value={symbolFilter} onChange={e => setSymbolFilter(e.target.value as SymbolFilter)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
                <option value="ALL">All symbols</option>
                <option value="NIFTY">NIFTY</option>
                <option value="BANKNIFTY">BANKNIFTY</option>
              </select>
              <select value={dirFilter} onChange={e => setDirFilter(e.target.value as DirFilter)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
                <option value="ALL">All directions</option>
                <option value="CALL">CALL</option>
                <option value="PUT">PUT</option>
              </select>
              <select value={outcomeFilter} onChange={e => setOutcomeFilter(e.target.value as OutcomeFilter)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
                <option value="ALL">All outcomes</option>
                <option value="TARGET_HIT">Target hit</option>
                <option value="SL_HIT">SL hit</option>
                <option value="EXPIRED">Expired</option>
                <option value="USER_CLOSED">Sold (manual)</option>
                <option value="OPEN">Open</option>
              </select>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-800/50">
                <tr>
                  <Th col="signal_time">Date/Time</Th>
                  <Th col="source">Source</Th>
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
                    <td colSpan={13} className="px-3 py-8 text-center text-gray-500">
                      No signals found for the selected filters
                    </td>
                  </tr>
                ) : sorted.map(s => (
                  <tr key={s.id} className="hover:bg-gray-800/50 transition-colors">
                    <td className="px-3 py-2 text-gray-400 whitespace-nowrap">
                      {s.signal_time
                        ? new Date(s.signal_time).toLocaleString('en-IN', {
                            year: 'numeric', month: 'short', day: 'numeric',
                            hour: '2-digit', minute: '2-digit',
                          })
                        : '—'}
                    </td>
                    <td className="px-3 py-2"><SourceBadge source={s.source} /></td>
                    <td className="px-3 py-2 font-medium text-white">{s.symbol}</td>
                    <td className="px-3 py-2">
                      <span className={`font-semibold ${s.direction === 'CALL' ? 'text-green-400' : 'text-red-400'}`}>
                        {s.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`font-medium ${s.confidence >= 75 ? 'text-purple-400' : 'text-blue-400'}`}>
                        {s.confidence}%
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(s.strategies_fired ?? []).map(strat => (
                          <span key={strat} className="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded">
                            {abbr(strat)}
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
                      {s.pnl != null
                        ? <span className={s.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>₹{s.pnl.toLocaleString('en-IN')}</span>
                        : <span className="text-gray-600">—</span>}
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
