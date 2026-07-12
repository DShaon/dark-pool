"use client";

/** Live kline stream (P3) — subscribes to the backend's WebSocket relay for
 *  one symbol+interval and exposes the latest tick. REST (`fetchKlines`)
 *  still owns historical backfill on load/symbol-switch; this hook carries
 *  only the live tail, updating as fast as trades arrive (sub-second during
 *  active trading) instead of waiting on a polling interval.
 *
 *  Auto-reconnects on drop; closes and reopens whenever symbol/interval
 *  change.
 */

import { useEffect, useRef, useState } from "react";

import { API, type Kline } from "@/lib/api";

const RECONNECT_MS = 2000;

function wsUrl(symbol: string, interval: string): string {
  const base = API.replace(/^http/, "ws");
  return `${base}/ws/kline/${symbol}/${interval}`;
}

export function useLiveKline(symbol: string, interval: string, enabled = true) {
  const [liveTick, setLiveTick] = useState<Kline | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let closedByEffect = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    setLiveTick(null); // a new symbol/interval starts with no live tick yet
    setConnected(false);

    // Disabled (e.g. forex — no free real-time forex WS): the caller's REST
    // poll is the price source instead. Never open the crypto stream for it.
    if (!enabled) return;

    const connect = () => {
      if (closedByEffect) return;
      socket = new WebSocket(wsUrl(symbol, interval));

      socket.onopen = () => setConnected(true);

      socket.onmessage = (ev) => {
        try {
          const candle: Kline = JSON.parse(ev.data);
          setLiveTick(candle);
        } catch {
          /* malformed frame — ignore, next tick will arrive shortly */
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (!closedByEffect) reconnectTimer = setTimeout(connect, RECONNECT_MS);
      };

      socket.onerror = () => socket?.close();
    };

    connect();

    return () => {
      closedByEffect = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [symbol, interval, enabled]);

  return { liveTick, connected };
}
