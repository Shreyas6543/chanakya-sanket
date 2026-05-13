import { useState, useEffect, useRef, useCallback } from 'react'

interface Candle {
  date: string
  t: string; ts: string
  o: number; h: number; l: number; c: number; v: number
}
interface TooltipData { candle: Candle; x: number; y: number }

// SVG layout constants (coordinate space)
const PRICE_H = 300
const VOL_H   = 60
const GAP     = 8
const PAD_L   = 68
const PAD_R   = 12
const PAD_T   = 16
const PAD_B   = 28
const TOTAL_H = PAD_T + PRICE_H + GAP + VOL_H + PAD_B
const MIN_CANDLE_PX = 6   // minimum px per candle before chart scrolls

function todayStr()      { return new Date().toISOString().slice(0, 10) }
function sevenDaysAgo()  {
  const d = new Date(); d.setDate(d.getDate() - 7)
  return d.toISOString().slice(0, 10)
}

function fmtDate(d: string) {
  return new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

// VWAP resets at the start of each trading day
function computeVwap(candles: Candle[]): number[] {
  let cumTP = 0, cumV = 0
  return candles.map((c, i) => {
    if (i === 0 || c.date !== candles[i - 1].date) { cumTP = 0; cumV = 0 }
    const tp = (c.h + c.l + c.c) / 3
    const v  = c.v > 0 ? c.v : 1
    cumTP += tp * v; cumV += v
    return cumTP / cumV
  })
}

function yLabels(min: number, max: number, count = 6): number[] {
  const step = (max - min) / (count - 1)
  return Array.from({ length: count }, (_, i) => min + i * step)
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <span className="text-xs text-gray-500 uppercase tracking-wide">{label}</span>
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
    </div>
  )
}

export default function CandlesPage() {
  const [symbol,    setSymbol]    = useState('NIFTY')
  const [startDate, setStartDate] = useState(sevenDaysAgo)
  const [endDate,   setEndDate]   = useState(todayStr)
  const [candles,   setCandles]   = useState<Candle[]>([])
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)
  const [tooltip,   setTooltip]   = useState<TooltipData | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const load = useCallback(() => {
    setLoading(true); setError(null)
    fetch(`/api/candles?symbol=${symbol}&start_date=${startDate}&end_date=${endDate}`)
      .then(r => r.json())
      .then((data: Candle[]) => { setCandles(data); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [symbol, startDate, endDate])

  useEffect(() => { load() }, [load])

  const n = candles.length

  // ── Scales ──────────────────────────────────────────────────────────────────
  // Expand SVG width so each candle is at least MIN_CANDLE_PX wide; enables horizontal scroll
  const SVG_W   = Math.max(900, n * MIN_CANDLE_PX + PAD_L + PAD_R)
  const chartW  = SVG_W - PAD_L - PAD_R
  const candleW = n > 0 ? chartW / n : 10
  const bodyW   = Math.max(1.5, candleW * 0.65)

  const allPrices = candles.flatMap(c => [c.h, c.l])
  const rawMin = n > 0 ? Math.min(...allPrices) : 0
  const rawMax = n > 0 ? Math.max(...allPrices) : 100
  const pad    = (rawMax - rawMin) * 0.06 || 1
  const minP   = rawMin - pad
  const maxP   = rawMax + pad
  const rangeP = maxP - minP

  const toY  = (p: number) => PAD_T + ((maxP - p) / rangeP) * PRICE_H
  const toX  = (i: number) => PAD_L + (i + 0.5) * candleW

  const maxVol  = n > 0 ? Math.max(...candles.map(c => c.v)) : 1
  const volBase = PAD_T + PRICE_H + GAP + VOL_H
  const toVolH  = (v: number) => maxVol > 0 ? (v / maxVol) * VOL_H : 0

  const vwap   = computeVwap(candles)
  const hasVol = candles.some(c => c.v > 0)

  // True when index is the first candle of a new trading day
  const isDayStart = (i: number) => i === 0 || candles[i].date !== candles[i - 1].date

  // VWAP path broken at day boundaries (M = moveto, L = lineto)
  const vwapPath = vwap.map((v, i) => {
    const x = toX(i), y = toY(v)
    return isDayStart(i) ? `M ${x} ${y}` : `L ${x} ${y}`
  }).join(' ')

  // ── Mouse hover ─────────────────────────────────────────────────────────────
  const onMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (n === 0 || !svgRef.current) return
    // Use createSVGPoint for accurate coords under any CSS transform or scroll
    const pt  = svgRef.current.createSVGPoint()
    pt.x = e.clientX; pt.y = e.clientY
    const svgP = pt.matrixTransform(svgRef.current.getScreenCTM()!.inverse())
    const idx  = Math.floor((svgP.x - PAD_L) / candleW)
    if (idx >= 0 && idx < n) {
      setTooltip({ candle: candles[idx], x: svgP.x, y: svgP.y })
    } else {
      setTooltip(null)
    }
  }

  const priceTicks = yLabels(minP, maxP, 6)
  // Time tick every N candles (skip if it falls on a day-start — already labelled there)
  const xStep      = Math.max(1, Math.ceil(n / 16))

  const change     = n > 0 ? candles[n - 1].c - candles[0].o : 0
  const changePct  = n > 0 ? (change / candles[0].o) * 100 : 0
  const bullishDay = change >= 0

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6 max-w-screen-2xl mx-auto">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">Candle Chart</h2>
          <p className="text-gray-500 text-sm">5-minute OHLCV · Local parquet cache</p>
        </div>

        {/* Controls */}
        <div className="flex gap-3 items-center flex-wrap">
          <select value={symbol} onChange={e => setSymbol(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500">
            <option value="NIFTY">NIFTY</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
          </select>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500" />
          <span className="text-gray-600 text-sm">to</span>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
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
        <div className="flex items-center justify-center h-64 text-gray-500">
          <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mr-3" />
          Loading candles…
        </div>
      )}

      {n === 0 && !loading && !error && (
        <div className="bg-gray-900 rounded-xl p-12 text-center text-gray-500">
          No candle data for {symbol} in selected range. Try a different date range (Mon–Fri trading days).
        </div>
      )}

      {n > 0 && (
        <>
          {/* Summary stats */}
          <div className="bg-gray-900 rounded-xl p-4 mb-4">
            <div className="flex flex-wrap gap-6 px-1">
              <Stat label="Open"    value={candles[0].o.toFixed(2)}                              color="text-white" />
              <Stat label="High"    value={Math.max(...candles.map(c => c.h)).toFixed(2)}         color="text-green-400" />
              <Stat label="Low"     value={Math.min(...candles.map(c => c.l)).toFixed(2)}         color="text-red-400" />
              <Stat label="Close"   value={candles[n - 1].c.toFixed(2)}                          color="text-white" />
              <Stat label="Change"
                value={`${bullishDay ? '+' : ''}${change.toFixed(2)} (${bullishDay ? '+' : ''}${changePct.toFixed(2)}%)`}
                color={bullishDay ? 'text-green-400' : 'text-red-400'} />
              <Stat label="Candles" value={String(n)}                                            color="text-gray-300" />
            </div>
          </div>

          {/* SVG Chart — scrolls horizontally when many candles */}
          <div className="bg-gray-900 rounded-xl p-4 mb-4">
            <div className="overflow-x-auto">
              <svg
                ref={svgRef}
                viewBox={`0 0 ${SVG_W} ${TOTAL_H}`}
                width={SVG_W}
                style={{ minWidth: '100%', cursor: 'crosshair', display: 'block' }}
                onMouseMove={onMouseMove}
                onMouseLeave={() => setTooltip(null)}
              >
                {/* Y axis price grid + labels */}
                {priceTicks.map((p, i) => (
                  <g key={i}>
                    <line x1={PAD_L} y1={toY(p)} x2={SVG_W - PAD_R} y2={toY(p)}
                      stroke="#1f2937" strokeWidth={0.5} strokeDasharray="3 3" />
                    <text x={PAD_L - 4} y={toY(p) + 4} textAnchor="end" fontSize={9} fill="#6b7280">
                      {p.toFixed(0)}
                    </text>
                  </g>
                ))}

                {/* Day boundary separators + date labels */}
                {candles.map((_, i) => !isDayStart(i) ? null : (
                  <g key={`day-${i}`}>
                    <line
                      x1={toX(i) - candleW / 2} y1={PAD_T}
                      x2={toX(i) - candleW / 2} y2={volBase}
                      stroke="#374151" strokeWidth={0.8}
                    />
                    <text
                      x={toX(i) - candleW / 2 + 4}
                      y={PAD_T + PRICE_H + GAP + VOL_H + PAD_B - 4}
                      fontSize={9} fill="#9ca3af"
                    >
                      {fmtDate(candles[i].date)}
                    </text>
                  </g>
                ))}

                {/* Intra-day time ticks (skip day-start slots — already labelled) */}
                {candles.map((c, i) => (!isDayStart(i) && i % xStep === 0) ? (
                  <text key={`xt-${i}`}
                    x={toX(i)} y={PAD_T + PRICE_H + GAP + VOL_H + PAD_B - 4}
                    textAnchor="middle" fontSize={9} fill="#4b5563">
                    {c.t}
                  </text>
                ) : null)}

                {/* VWAP — broken path so it resets per day */}
                <path d={vwapPath} fill="none" stroke="#a855f7"
                  strokeWidth={1.2} strokeDasharray="4 2" opacity={0.8} />

                {/* Candles */}
                {candles.map((c, i) => {
                  const x       = toX(i)
                  const bull    = c.c >= c.o
                  const color   = bull ? '#22c55e' : '#ef4444'
                  const bodyTop = toY(Math.max(c.o, c.c))
                  const bodyBot = toY(Math.min(c.o, c.c))
                  const bodyH   = Math.max(1, bodyBot - bodyTop)
                  return (
                    <g key={i}>
                      <line x1={x} y1={toY(c.h)} x2={x} y2={toY(c.l)} stroke={color} strokeWidth={1} />
                      <rect x={x - bodyW / 2} y={bodyTop} width={bodyW} height={bodyH}
                        fill={color} stroke={color} strokeWidth={0.5} opacity={0.9} />
                    </g>
                  )
                })}

                {/* Volume bars */}
                {hasVol && candles.map((c, i) => {
                  const x  = toX(i)
                  const vh = toVolH(c.v)
                  const bull = c.c >= c.o
                  return (
                    <rect key={`v${i}`}
                      x={x - bodyW / 2} y={volBase - vh}
                      width={bodyW} height={vh}
                      fill={bull ? '#16a34a' : '#dc2626'} opacity={0.5}
                    />
                  )
                })}

                <text x={PAD_L - 4} y={PAD_T + PRICE_H + GAP + VOL_H / 2 + 4}
                  textAnchor="end" fontSize={8} fill="#4b5563">Vol</text>

                {/* Hover crosshair + tooltip */}
                {tooltip && (() => {
                  const { candle: c, x: mx } = tooltip
                  const bull = c.c >= c.o
                  const tipW = 152, tipH = 126
                  const tipX = mx + 8 + tipW > SVG_W ? mx - tipW - 8 : mx + 8
                  const tipY = PAD_T + 4
                  return (
                    <g>
                      <line x1={mx} y1={PAD_T} x2={mx} y2={PAD_T + PRICE_H}
                        stroke="#374151" strokeWidth={1} strokeDasharray="3 2" />
                      <rect x={tipX} y={tipY} width={tipW} height={tipH}
                        fill="#111827" stroke="#374151" strokeWidth={1} rx={4} />
                      <text x={tipX + 8} y={tipY + 14} fontSize={9} fill="#6b7280">{fmtDate(c.date)}</text>
                      <text x={tipX + 8} y={tipY + 27} fontSize={10} fill="#d1d5db" fontWeight="600">{c.t}</text>
                      {[
                        ['O', c.o.toFixed(2), '#9ca3af'],
                        ['H', c.h.toFixed(2), '#22c55e'],
                        ['L', c.l.toFixed(2), '#ef4444'],
                        ['C', c.c.toFixed(2), bull ? '#22c55e' : '#ef4444'],
                        ['V', c.v.toLocaleString('en-IN'), '#a855f7'],
                      ].map(([label, val, col], idx) => (
                        <g key={label}>
                          <text x={tipX + 8}  y={tipY + 43 + idx * 16} fontSize={9} fill="#6b7280">{label}</text>
                          <text x={tipX + 22} y={tipY + 43 + idx * 16} fontSize={9} fill={col as string}>{val}</text>
                        </g>
                      ))}
                    </g>
                  )
                })()}
              </svg>
            </div>

            {/* Legend */}
            <div className="flex gap-4 mt-2 px-1 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <span className="inline-block w-6 h-0.5 bg-purple-500 opacity-75" style={{ borderTop: '1px dashed' }} />
                VWAP
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 bg-green-500 rounded-sm opacity-80" /> Bullish
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 bg-red-500 rounded-sm opacity-80" /> Bearish
              </span>
              {!hasVol && <span className="text-gray-600">(Volume = 0 for index instruments)</span>}
            </div>
          </div>

          {/* Data Table */}
          <div className="bg-gray-900 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-gray-400 mb-3">
              Candle Data <span className="text-gray-600 font-normal">({n} rows)</span>
            </h3>
            <div className="overflow-auto max-h-96">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-gray-900 z-10">
                  <tr className="text-gray-500 uppercase tracking-wide border-b border-gray-800">
                    <th className="text-left py-2 pr-4 font-medium">Date</th>
                    <th className="text-left py-2 pr-4 font-medium">Time</th>
                    <th className="text-right py-2 pr-4 font-medium">Open</th>
                    <th className="text-right py-2 pr-4 font-medium">High</th>
                    <th className="text-right py-2 pr-4 font-medium">Low</th>
                    <th className="text-right py-2 pr-4 font-medium">Close</th>
                    <th className="text-right py-2 pr-4 font-medium">Volume</th>
                    <th className="text-right py-2 font-medium">Chg%</th>
                  </tr>
                </thead>
                <tbody>
                  {candles.map((c, i) => {
                    const bull     = c.c >= c.o
                    const prevClose = i > 0 ? candles[i - 1].c : c.o
                    const chgPct   = ((c.c - prevClose) / prevClose) * 100
                    const dayStart = isDayStart(i)
                    return (
                      <tr key={i}
                        className={`border-b border-gray-800/50 hover:bg-gray-800/30 ${dayStart && i > 0 ? 'border-t border-t-gray-700' : ''}`}>
                        <td className="py-1.5 pr-4 text-gray-500 whitespace-nowrap">
                          {dayStart ? fmtDate(c.date) : ''}
                        </td>
                        <td className="py-1.5 pr-4 text-gray-300 font-mono">{c.t}</td>
                        <td className="py-1.5 pr-4 text-right text-gray-300 font-mono">{c.o.toFixed(2)}</td>
                        <td className="py-1.5 pr-4 text-right text-green-400 font-mono">{c.h.toFixed(2)}</td>
                        <td className="py-1.5 pr-4 text-right text-red-400 font-mono">{c.l.toFixed(2)}</td>
                        <td className={`py-1.5 pr-4 text-right font-mono font-medium ${bull ? 'text-green-400' : 'text-red-400'}`}>
                          {c.c.toFixed(2)}
                        </td>
                        <td className="py-1.5 pr-4 text-right text-gray-400 font-mono">
                          {c.v > 0 ? c.v.toLocaleString('en-IN') : '—'}
                        </td>
                        <td className={`py-1.5 text-right font-mono font-medium ${chgPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {chgPct >= 0 ? '+' : ''}{chgPct.toFixed(2)}%
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
