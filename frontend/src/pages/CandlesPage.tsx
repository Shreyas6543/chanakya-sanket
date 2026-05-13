import { useState, useEffect, useRef, useCallback } from 'react'

interface Candle { t: string; ts: string; o: number; h: number; l: number; c: number; v: number }
interface TooltipData { candle: Candle; x: number; y: number }

// SVG layout constants
const W = 900
const PRICE_H  = 300
const VOL_H    = 60
const GAP      = 8
const PAD_L    = 68
const PAD_R    = 12
const PAD_T    = 16
const PAD_B    = 28
const TOTAL_H  = PAD_T + PRICE_H + GAP + VOL_H + PAD_B

function todayStr() { return new Date().toISOString().slice(0, 10) }

function computeVwap(candles: Candle[]): number[] {
  let cumTP = 0, cumV = 0
  return candles.map(c => {
    const tp = (c.h + c.l + c.c) / 3
    const v  = c.v > 0 ? c.v : 1   // equal-weight for 0-volume indices
    cumTP += tp * v
    cumV  += v
    return cumTP / cumV
  })
}

function yLabels(min: number, max: number, count = 6): number[] {
  const step = (max - min) / (count - 1)
  return Array.from({ length: count }, (_, i) => min + i * step)
}

export default function CandlesPage() {
  const [symbol, setSymbol]     = useState('NIFTY')
  const [date, setDate]         = useState(todayStr)
  const [candles, setCandles]   = useState<Candle[]>([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [tooltip, setTooltip]   = useState<TooltipData | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const load = useCallback(() => {
    setLoading(true); setError(null)
    fetch(`/api/candles?symbol=${symbol}&date=${date}`)
      .then(r => r.json())
      .then((data: Candle[]) => { setCandles(data); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [symbol, date])

  useEffect(() => { load() }, [load])

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-500">
      <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mr-3" />
      Loading candles…
    </div>
  )

  const n = candles.length

  // ── Scales ──────────────────────────────────────────────────────────────────
  const chartW  = W - PAD_L - PAD_R
  const candleW = n > 0 ? chartW / n : 10
  const bodyW   = Math.max(1.5, candleW * 0.65)

  const allPrices = candles.flatMap(c => [c.h, c.l])
  const rawMin = n > 0 ? Math.min(...allPrices) : 0
  const rawMax = n > 0 ? Math.max(...allPrices) : 100
  const pad    = (rawMax - rawMin) * 0.06 || 1
  const minP   = rawMin - pad
  const maxP   = rawMax + pad
  const rangeP = maxP - minP

  const toY   = (p: number) => PAD_T + ((maxP - p) / rangeP) * PRICE_H
  const toX   = (i: number) => PAD_L + (i + 0.5) * candleW

  const maxVol   = n > 0 ? Math.max(...candles.map(c => c.v)) : 1
  const volBase  = PAD_T + PRICE_H + GAP + VOL_H
  const toVolH   = (v: number) => maxVol > 0 ? (v / maxVol) * VOL_H : 0

  const vwap = computeVwap(candles)
  const hasVol = candles.some(c => c.v > 0)

  // ── Mouse hover ─────────────────────────────────────────────────────────────
  const onMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (n === 0 || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const svgX  = ((e.clientX - rect.left) / rect.width)  * W
    const svgY  = ((e.clientY - rect.top)  / rect.height) * TOTAL_H
    const idx   = Math.floor((svgX - PAD_L) / candleW)
    if (idx >= 0 && idx < n) {
      setTooltip({ candle: candles[idx], x: svgX, y: svgY })
    } else {
      setTooltip(null)
    }
  }

  // Y axis price ticks
  const priceTicks = yLabels(minP, maxP, 6)

  // X axis time ticks — show every nth label
  const xStep = Math.ceil(n / 10)

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
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
          >
            <option value="NIFTY">NIFTY</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
          </select>
          <input
            type="date" value={date}
            onChange={e => setDate(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
          />
          <button
            onClick={load}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition-colors"
          >
            Load
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg px-4 py-3 mb-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {n === 0 && !loading && (
        <div className="bg-gray-900 rounded-xl p-12 text-center text-gray-500">
          No candle data for {symbol} on {date}. Try a trading day (Mon–Fri).
        </div>
      )}

      {n > 0 && (
        <div className="bg-gray-900 rounded-xl p-4">

          {/* Day summary */}
          <div className="flex flex-wrap gap-6 mb-4 px-1">
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Open</span>
              <div className="text-lg font-semibold text-white">{candles[0].o.toFixed(2)}</div>
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">High</span>
              <div className="text-lg font-semibold text-green-400">
                {Math.max(...candles.map(c => c.h)).toFixed(2)}
              </div>
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Low</span>
              <div className="text-lg font-semibold text-red-400">
                {Math.min(...candles.map(c => c.l)).toFixed(2)}
              </div>
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Close</span>
              <div className="text-lg font-semibold text-white">{candles[n - 1].c.toFixed(2)}</div>
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Change</span>
              <div className={`text-lg font-semibold ${bullishDay ? 'text-green-400' : 'text-red-400'}`}>
                {bullishDay ? '+' : ''}{change.toFixed(2)} ({bullishDay ? '+' : ''}{changePct.toFixed(2)}%)
              </div>
            </div>
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Candles</span>
              <div className="text-lg font-semibold text-gray-300">{n}</div>
            </div>
          </div>

          {/* SVG Chart */}
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${TOTAL_H}`}
            width="100%"
            onMouseMove={onMouseMove}
            onMouseLeave={() => setTooltip(null)}
            style={{ cursor: 'crosshair' }}
          >
            {/* ── Y axis price labels ── */}
            {priceTicks.map((p, i) => (
              <g key={i}>
                <line
                  x1={PAD_L} y1={toY(p)} x2={W - PAD_R} y2={toY(p)}
                  stroke="#1f2937" strokeWidth={0.5} strokeDasharray="3 3"
                />
                <text x={PAD_L - 4} y={toY(p) + 4} textAnchor="end" fontSize={9} fill="#6b7280">
                  {p.toFixed(0)}
                </text>
              </g>
            ))}

            {/* ── X axis time labels ── */}
            {candles.map((c, i) => i % xStep === 0 && (
              <text key={i} x={toX(i)} y={PAD_T + PRICE_H + GAP + VOL_H + PAD_B - 4}
                textAnchor="middle" fontSize={9} fill="#6b7280">
                {c.t}
              </text>
            ))}

            {/* ── VWAP line ── */}
            <polyline
              points={vwap.map((v, i) => `${toX(i)},${toY(v)}`).join(' ')}
              fill="none"
              stroke="#a855f7"
              strokeWidth={1.2}
              strokeDasharray="4 2"
              opacity={0.8}
            />

            {/* ── Candles ── */}
            {candles.map((c, i) => {
              const x       = toX(i)
              const bull    = c.c >= c.o
              const color   = bull ? '#22c55e' : '#ef4444'
              const bodyTop = toY(Math.max(c.o, c.c))
              const bodyBot = toY(Math.min(c.o, c.c))
              const bodyH   = Math.max(1, bodyBot - bodyTop)
              return (
                <g key={i}>
                  {/* Wick */}
                  <line x1={x} y1={toY(c.h)} x2={x} y2={toY(c.l)} stroke={color} strokeWidth={1} />
                  {/* Body */}
                  <rect
                    x={x - bodyW / 2} y={bodyTop}
                    width={bodyW} height={bodyH}
                    fill={bull ? color : color}
                    stroke={color} strokeWidth={0.5}
                    opacity={0.9}
                  />
                </g>
              )
            })}

            {/* ── Volume bars ── */}
            {hasVol && candles.map((c, i) => {
              const x  = toX(i)
              const vh = toVolH(c.v)
              const bull = c.c >= c.o
              return (
                <rect
                  key={`v${i}`}
                  x={x - bodyW / 2} y={volBase - vh}
                  width={bodyW} height={vh}
                  fill={bull ? '#16a34a' : '#dc2626'}
                  opacity={0.5}
                />
              )
            })}

            {/* Volume axis label */}
            <text x={PAD_L - 4} y={PAD_T + PRICE_H + GAP + VOL_H / 2 + 4}
              textAnchor="end" fontSize={8} fill="#4b5563">
              Vol
            </text>

            {/* ── Hover tooltip ── */}
            {tooltip && (() => {
              const { candle: c, x: mx } = tooltip
              const bull  = c.c >= c.o
              const tipW  = 130
              const tipH  = 110
              const tipX  = mx + 8 + tipW > W ? mx - tipW - 8 : mx + 8
              const tipY  = PAD_T + 4
              return (
                <g>
                  <line x1={mx} y1={PAD_T} x2={mx} y2={PAD_T + PRICE_H} stroke="#374151" strokeWidth={1} strokeDasharray="3 2" />
                  <rect x={tipX} y={tipY} width={tipW} height={tipH} fill="#111827" stroke="#374151" strokeWidth={1} rx={4} />
                  <text x={tipX + 8} y={tipY + 16} fontSize={10} fill="#d1d5db" fontWeight="600">{c.t}</text>
                  {[
                    ['O', c.o.toFixed(2), '#9ca3af'],
                    ['H', c.h.toFixed(2), '#22c55e'],
                    ['L', c.l.toFixed(2), '#ef4444'],
                    ['C', c.c.toFixed(2), bull ? '#22c55e' : '#ef4444'],
                    ['V', c.v.toLocaleString(), '#a855f7'],
                  ].map(([label, val, col], i) => (
                    <g key={label}>
                      <text x={tipX + 8}  y={tipY + 32 + i * 16} fontSize={9} fill="#6b7280">{label}</text>
                      <text x={tipX + 22} y={tipY + 32 + i * 16} fontSize={9} fill={col as string}>{val}</text>
                    </g>
                  ))}
                </g>
              )
            })()}
          </svg>

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
      )}
    </div>
  )
}
