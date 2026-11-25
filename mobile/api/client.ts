import axios from 'axios';

export const API_BASE = 'https://stockpred-production-9af497e9.up.railway.app';

let _tokenGetter: (() => string | null) = () => null;
export const setTokenGetter = (fn: () => string | null) => { _tokenGetter = fn; };

const getToken = () => {
  const fromGetter = _tokenGetter();
  if (fromGetter) return fromGetter;
  try {
    const raw = localStorage.getItem('auth-storage');
    if (raw) return JSON.parse(raw)?.state?.token ?? null;
  } catch {}
  return null;
};

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});