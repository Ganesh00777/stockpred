import axios from 'axios';

// ── Change this to your Railway URL after deploy ──
export const API_BASE = __DEV__
  ? 'http://localhost:8000'
  : 'https://stockpred-production-9af497e9.up.railway.app';

export const WS_BASE = API_BASE.replace('http', 'ws');

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token from store
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Token getter — avoids circular import with store
let _tokenGetter: (() => string | null) = () => null;
export const setTokenGetter = (fn: () => string | null) => { _tokenGetter = fn; };
const getToken = () => _tokenGetter();
