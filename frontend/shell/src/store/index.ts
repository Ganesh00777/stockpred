import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Signal {
  symbol: string
  exchange: string
  direction: number       // 1=buy, -1=sell, 0=hold
  confidence: number
  volume_score: number
  momentum_score: number
  news_score: number
  reasons: string[]
  price: number
  volume_ratio: number
  generated_at: string
}

export interface Breakout {
  symbol: string
  exchange: string
  today_volume: number
  avg_volume_20d: number
  volume_ratio: number
  close: number
  pct_change: number
}

interface AppState {
  // Auth
  accessToken: string | null
  user: { email: string; tier: string } | null
  setAuth: (token: string, user: any) => void
  logout: () => void

  // Signals
  signals: Signal[]
  breakouts: Breakout[]
  signalsLoading: boolean
  setSignals: (signals: Signal[]) => void
  setBreakouts: (breakouts: Breakout[]) => void
  setSignalsLoading: (v: boolean) => void

  // Watchlist
  watchlist: string[]
  addToWatchlist: (symbol: string) => void
  removeFromWatchlist: (symbol: string) => void

  // Active symbol (for chart MFE)
  activeSymbol: string | null
  activeExchange: string
  setActiveSymbol: (symbol: string, exchange: string) => void

  // Filter state
  minConfidence: number
  directionFilter: number | null   // null=all, 1=buy, -1=sell
  setFilters: (minConf: number, dir: number | null) => void
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      // Auth
      accessToken: null,
      user: null,
      setAuth: (token, user) => set({ accessToken: token, user }),
      logout: () => set({ accessToken: null, user: null }),

      // Signals
      signals: [],
      breakouts: [],
      signalsLoading: false,
      setSignals: (signals) => set({ signals }),
      setBreakouts: (breakouts) => set({ breakouts }),
      setSignalsLoading: (v) => set({ signalsLoading: v }),

      // Watchlist
      watchlist: ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'AAPL'],
      addToWatchlist: (symbol) =>
        set((s) => ({ watchlist: [...new Set([...s.watchlist, symbol])] })),
      removeFromWatchlist: (symbol) =>
        set((s) => ({ watchlist: s.watchlist.filter((w) => w !== symbol) })),

      // Active symbol
      activeSymbol: null,
      activeExchange: 'NSE',
      setActiveSymbol: (symbol, exchange) => set({ activeSymbol: symbol, activeExchange: exchange }),

      // Filters
      minConfidence: 0.4,
      directionFilter: null,
      setFilters: (minConf, dir) => set({ minConfidence: minConf, directionFilter: dir }),
    }),
    { name: 'stockpred-store', partialize: (s) => ({ watchlist: s.watchlist, accessToken: s.accessToken, user: s.user }) }
  )
)
