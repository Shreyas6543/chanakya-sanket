import { useState, useEffect, useRef } from 'react'

// /api/debug/live-prices returns { live_prices: { NIFTY: 22450.5, BANKNIFTY: 48200.0 } }
interface LivePricesResponse {
  live_prices: Record<string, number>
}

const SYMBOLS = ['NIFTY', 'BANKNIFTY'] as const

function fmt(n: number) {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

export default function LivePrices() {
  const [prices, setPrices]   = useState<Record<string, number>>({})
  const [prevPrices, setPrev] = useState<Record<string, number>>({})
  const [active, setActive]   = useState(false)
  const [error, setError]     = useState(false)
  const intervalRef           = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = async () => {
    try {
      const res = await fetch('/api/debug/live-prices')
      if (!res.ok) throw new Error()
      const data = await res.json() as LivePricesResponse
      setPrev(prev => ({ ...prev }))
      setPrices(curr => {
        setPrev(curr)
        return data.live_prices
      })
      setActive(true)
      setError(false)
    } catch {
      setActive(false)
      setError(true)
    }
  }

  useEffect(() => {
    void poll()
    intervalRef.current = setInterval(() => { void poll() }, 5000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Hide entirely when server is down and no prices yet
  const hasAny = SYMBOLS.some(s => prices[s] != null)
  if (!hasAny && error) return null

  return (
    <div className="flex items-center gap-5 px-4 py-2.5 bg-gray-900 rounded-xl">
      {/* Status dot */}
      <div className="flex items-center gap-1.5 shrink-0">
        <span className={`w-2 h-2 rounded-full ${active ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
        <span className="text-xs text-gray-500 uppercase tracking-wider">Live</span>
      </div>

      {SYMBOLS.map(sym => {
        const price = prices[sym]
        const prev  = prevPrices[sym]
        const up    = prev != null && price != null && price > prev
        const down  = prev != null && price != null && price < prev

        return (
          <div key={sym} className="flex items-center gap-2">
            <span className="text-xs text-gray-400 font-medium shrink-0">{sym}</span>
            {price != null
              ? (
                <span className={`text-sm font-semibold tabular-nums transition-colors duration-500 ${
                  up ? 'text-green-400' : down ? 'text-red-400' : 'text-white'
                }`}>
                  {fmt(price)}
                </span>
              )
              : <span className="text-sm text-gray-600">—</span>
            }
          </div>
        )
      })}

      <span className="ml-auto text-xs text-gray-700 shrink-0">5s</span>
    </div>
  )
}
