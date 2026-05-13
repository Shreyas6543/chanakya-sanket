// ── Signal states ────────────────────────────────────────────────────────────

export type SignalState = 'OPEN' | 'TARGET_HIT' | 'SL_HIT' | 'EXPIRED' | 'USER_CLOSED'
export type Direction   = 'CALL' | 'PUT'
export type Regime      = 'TRENDING' | 'SIDEWAYS'
export type Source      = 'live' | 'historical' | 'mock' | 'shadow'

// ── Per-signal row returned by /api/dashboard ────────────────────────────────

export interface Signal {
  id:               number
  symbol:           string
  direction:        Direction
  strike:           number
  expiry:           string
  entry:            number
  sl:               number
  target:           number
  confidence:       number
  regime:           Regime
  outcome:          SignalState
  pnl:              number | null
  capital_required: number
  source:           Source
  signal_time:      string | null   // ISO string from signal_context
  hour:             number | null
  strategies_fired: string[]
}

// ── Overview block ────────────────────────────────────────────────────────────

export interface Overview {
  total_signals: number
  wins:          number
  losses:        number
  expired:       number
  open:          number
  win_rate:      number
  total_pnl:     number
}

// ── Analytics breakdown rows ──────────────────────────────────────────────────

export interface BySymbol {
  symbol:   string
  total:    number
  wins:     number
  win_rate: number
  pnl:      number
}

export interface ByDirection {
  direction: Direction
  total:     number
  wins:      number
  win_rate:  number
}

export interface ByHour {
  hour:     number
  total:    number
  wins:     number
  win_rate: number
}

export interface ByCombo {
  combo:    string
  total:    number
  wins:     number
  win_rate: number
}

// ── Full dashboard response from /api/dashboard ───────────────────────────────

export interface DashboardData {
  overview:            Overview
  by_symbol:           BySymbol[]
  by_direction:        ByDirection[]
  signals:             Signal[]
  filters: {
    start_date: string
    end_date:   string
    strategies: string | null
  }
}

// ── Filters used in the UI ────────────────────────────────────────────────────

export type SymbolFilter  = 'ALL' | 'NIFTY' | 'BANKNIFTY'
export type DirFilter     = 'ALL' | Direction
export type OutcomeFilter = 'ALL' | SignalState
export type SourceFilter  = 'ALL' | Source

export type SortKey = keyof Signal
