import { useState, useRef, useEffect } from 'react'

const SUGGESTED = [
  'Why is my win rate where it is?',
  'Which symbol is performing better and why?',
  'What time of day should I focus on?',
  'Is CALL or PUT working better for me?',
  'What are the main weaknesses in my current data?',
  'How do my expired signals affect the overall picture?',
]

export default function ClaudePanel({ dashboardData }) {
  const [question, setQuestion]   = useState('')
  const [response, setResponse]   = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const responseRef               = useRef(null)
  const abortRef                  = useRef(null)

  // Auto-scroll response box as text streams in
  useEffect(() => {
    if (responseRef.current) {
      responseRef.current.scrollTop = responseRef.current.scrollHeight
    }
  }, [response])

  const ask = async (q) => {
    const text = (q || question).trim()
    if (!text || loading) return

    setQuestion(text)
    setResponse('')
    setError(null)
    setLoading(true)

    // Cancel any in-flight request
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    try {
      const res = await fetch('/api/ai/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, context: dashboardData }),
        signal: abortRef.current.signal,
      })

      if (!res.ok) throw new Error(`API error ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const chunk = line.slice(6)
          if (chunk === '[DONE]') { setLoading(false); return }
          setResponse(prev => prev + chunk)
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const hasData = dashboardData && dashboardData.overview

  return (
    <div className="bg-gray-900 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-white flex items-center gap-2">
            <span className="text-purple-400">✦</span> Ask Chanakya AI
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Claude analyses your current signal data — {hasData ? `${dashboardData.overview.total_signals} signals loaded` : 'load data first using the filters above'}
          </p>
        </div>
        {loading && (
          <div className="flex items-center gap-2 text-xs text-purple-400">
            <div className="w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
            Thinking…
          </div>
        )}
      </div>

      <div className="p-5 space-y-4">
        {/* Suggested questions */}
        {!response && !loading && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTED.map(s => (
              <button
                key={s}
                onClick={() => ask(s)}
                disabled={!hasData}
                className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 border border-gray-700 hover:border-gray-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && ask()}
            placeholder={hasData ? 'Ask anything about your trading data…' : 'Load signals above first'}
            disabled={!hasData || loading}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 disabled:opacity-50"
          />
          <button
            onClick={() => ask()}
            disabled={!hasData || loading || !question.trim()}
            className="px-4 py-2.5 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Ask
          </button>
          {(response || loading) && (
            <button
              onClick={() => { setResponse(''); setQuestion(''); if (abortRef.current) abortRef.current.abort(); setLoading(false) }}
              className="px-3 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg text-sm transition-colors"
            >
              Clear
            </button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {/* Streaming response */}
        {(response || loading) && (
          <div
            ref={responseRef}
            className="bg-gray-800/60 border border-gray-700 rounded-xl px-5 py-4 text-sm text-gray-200 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto"
          >
            {response}
            {loading && (
              <span className="inline-block w-1.5 h-4 bg-purple-400 ml-0.5 animate-pulse rounded-sm" />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
