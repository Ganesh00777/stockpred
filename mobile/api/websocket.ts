import { WS_BASE } from './client';
import { Signal } from './signals';

type SignalHandler = (signal: Signal) => void;

class SignalWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Set<SignalHandler> = new Set();
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;

  connect() {
    this.shouldReconnect = true;
    this._connect();
  }

  private _connect() {
    try {
      this.ws = new WebSocket(`${WS_BASE}/ws/signals`);

      this.ws.onopen = () => {
        console.log('[WS] Connected to signal feed');
        // Keepalive ping every 25s
        this.pingInterval = setInterval(() => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'signal') {
            this.handlers.forEach(h => h(msg.data as Signal));
          }
        } catch (e) {
          console.warn('[WS] Parse error:', e);
        }
      };

      this.ws.onclose = () => {
        console.log('[WS] Disconnected');
        this._cleanup();
        if (this.shouldReconnect) {
          this.reconnectTimeout = setTimeout(() => this._connect(), 3000);
        }
      };

      this.ws.onerror = (err) => {
        console.warn('[WS] Error:', err);
      };
    } catch (e) {
      console.warn('[WS] Failed to connect:', e);
    }
  }

  subscribe(handler: SignalHandler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  disconnect() {
    this.shouldReconnect = false;
    this._cleanup();
    this.ws?.close();
    this.ws = null;
  }

  private _cleanup() {
    if (this.pingInterval) { clearInterval(this.pingInterval); this.pingInterval = null; }
    if (this.reconnectTimeout) { clearTimeout(this.reconnectTimeout); this.reconnectTimeout = null; }
  }
}

export const signalWS = new SignalWebSocket();
