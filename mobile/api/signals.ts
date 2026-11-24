import { api } from './client';

export interface Signal {
  id: number;
  symbol: string;
  exchange: string;
  direction: 1 | -1;
  confidence: number;
  volume_score: number;
  momentum_score: number;
  news_score: number;
  signal_reasons: string[];
  price_at_signal: number;
  volume_ratio: number;
  created_at: string;
}

export interface Breakout {
  symbol: string;
  exchange: string;
  volume_ratio: number;
  close: number;
  pct_change: number;
}

export interface BacktestResult {
  symbol: string;
  total_signals: number;
  correct: number;
  win_rate: number;
  avg_return_5d: number;
  buy_accuracy: number;
  sell_accuracy: number;
  signals: Signal[];
}

export interface NewsItem {
  headline: string;
  source: string;
  url: string;
  published_at: string;
  finbert_label: 'positive' | 'negative' | 'neutral';
  finbert_score: number;
}

// ── Signals ───────────────────────────────────────────────────────────────────
export const fetchSignals = async (params?: {
  min_confidence?: number;
  direction?: number;
  exchange?: string;
  symbols?: string[];
}): Promise<Signal[]> => {
  const { data } = await api.get('/signals', { params });
  return data;
};

export const fetchBreakouts = async (min_ratio = 2.0): Promise<Breakout[]> => {
  const { data } = await api.get('/signals/breakouts', { params: { min_ratio } });
  return data;
};

export const fetchSignalHistory = async (symbol: string): Promise<Signal[]> => {
  const { data } = await api.get(`/signals/${symbol}/history`);
  return data;
};

// ── Candles ───────────────────────────────────────────────────────────────────
export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export const fetchCandles = async (
  symbol: string,
  period = '3mo',
  interval = '1d'
): Promise<Candle[]> => {
  const { data } = await api.get(`/candles/${symbol}`, { params: { period, interval } });
  return data;
};

// ── News ──────────────────────────────────────────────────────────────────────
export const fetchNews = async (symbol: string): Promise<NewsItem[]> => {
  const { data } = await api.get('/news', { params: { symbol } });
  return data;
};

// ── Backtest ──────────────────────────────────────────────────────────────────
export const fetchBacktest = async (symbol: string): Promise<BacktestResult> => {
  const { data } = await api.get(`/backtest/${symbol}`);
  return data;
};

// ── Alerts ────────────────────────────────────────────────────────────────────
export interface AlertRule {
  id: number;
  symbol: string;
  exchange: string;
  direction: number | null;
  min_confidence: number;
  channel: 'telegram' | 'email' | 'both';
  active: boolean;
}

export const fetchAlerts = async (): Promise<AlertRule[]> => {
  const { data } = await api.get('/alerts');
  return data;
};

export const createAlert = async (rule: Omit<AlertRule, 'id'>): Promise<AlertRule> => {
  const { data } = await api.post('/alerts', rule);
  return data;
};

export const deleteAlert = async (id: number): Promise<void> => {
  await api.delete(`/alerts/${id}`);
};

export const toggleAlert = async (id: number, active: boolean): Promise<AlertRule> => {
  const { data } = await api.patch(`/alerts/${id}`, { active });
  return data;
};
