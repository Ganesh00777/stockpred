import { create } from 'zustand';
import { Signal, Breakout, AlertRule } from '../api/signals';

interface Filters {
  minConfidence: number;
  direction: 1 | -1 | null;
  exchange: 'ALL' | 'NSE' | 'NASDAQ';
  minVolRatio: number;
}

interface AppState {
  // Auth
  accessToken: string | null;
  user: { id: number; email: string; name: string } | null;
  setAuth: (token: string, user: AppState['user']) => void;
  clearAuth: () => void;

  // Signals
  signals: Signal[];
  breakouts: Breakout[];
  setSignals: (s: Signal[]) => void;
  setBreakouts: (b: Breakout[]) => void;
  prependSignal: (s: Signal) => void;  // live WS push

  // Watchlist
  watchlist: string[];
  addToWatchlist: (symbol: string) => void;
  removeFromWatchlist: (symbol: string) => void;

  // Active symbol (chart focus)
  activeSymbol: string;
  activeExchange: string;
  setActiveSymbol: (symbol: string, exchange: string) => void;

  // Filters
  filters: Filters;
  setFilter: <K extends keyof Filters>(key: K, value: Filters[K]) => void;

  // Alerts
  alerts: AlertRule[];
  setAlerts: (a: AlertRule[]) => void;
}

export const useStore = create<AppState>((set) => ({
  // Auth
  accessToken: null,
  user: null,
  setAuth: (accessToken, user) => set({ accessToken, user }),
  clearAuth: () => set({ accessToken: null, user: null }),

  // Signals
  signals: [],
  breakouts: [],
  setSignals: (signals) => set({ signals }),
  setBreakouts: (breakouts) => set({ breakouts }),
  prependSignal: (signal) =>
    set((s) => ({
      signals: [signal, ...s.signals.filter((x) => x.id !== signal.id)].slice(0, 100),
    })),

  // Watchlist
  watchlist: ['RELIANCE', 'TCS', 'INFY', 'NVDA', 'AMD', 'HDFCBANK', 'TATASTEEL'],
  addToWatchlist: (symbol) =>
    set((s) => ({ watchlist: s.watchlist.includes(symbol) ? s.watchlist : [...s.watchlist, symbol] })),
  removeFromWatchlist: (symbol) =>
    set((s) => ({ watchlist: s.watchlist.filter((w) => w !== symbol) })),

  // Active symbol
  activeSymbol: 'RELIANCE',
  activeExchange: 'NSE',
  setActiveSymbol: (activeSymbol, activeExchange) => set({ activeSymbol, activeExchange }),

  // Filters
  filters: { minConfidence: 0.4, direction: null, exchange: 'ALL', minVolRatio: 2.0 },
  setFilter: (key, value) =>
    set((s) => ({ filters: { ...s.filters, [key]: value } })),

  // Alerts
  alerts: [],
  setAlerts: (alerts) => set({ alerts }),
}));
