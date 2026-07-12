"use client";

/** Watchlist rail (ADR-0011: sparkline tiles). LIVE PRICE (P3): each crypto
 *  tile carries its own WebSocket tick (the same `BinanceStreamHub` the main
 *  chart uses — the backend shares one upstream Binance subscription per
 *  symbol+interval across every local subscriber, so watching a symbol here
 *  AND on the main chart costs nothing extra upstream). REST refreshes the
 *  24h sparkline shape every 60s; the live tick moves the price, the 24h
 *  change%, and the sparkline's last point in between polls.
 *
 *  ASSET CLASS (P4): the rail is scoped to the active class. Crypto and forex
 *  keep independent boards (`dp:watchlist:{class}` in localStorage) and
 *  independent defaults. Forex has no free real-time WS, so forex tiles are
 *  REST-polled only (the live tick is disabled) and render their pair as
 *  `EUR/USD`, not `EUR/USDT`. The parent remounts this rail on a class switch
 *  (via `key`), so state never leaks across classes.
 *
 *  The board persists in localStorage (single-user P1; server-side
 *  persistence arrives with the DB) and mirrors to the backend scanner so
 *  Active mode watches whatever class the desk is on. Add via the input,
 *  remove via ×.
 */

import { memo, useCallback, useEffect, useState } from "react";

import type { AssetClass } from "@/components/MarketToggle";
import SourceBadge from "@/components/SourceBadge";
import Term from "@/components/Term";
import { fetchKlines, formatPrice, syncWatchlist, type Kline } from "@/lib/api";
import { useLiveKline } from "@/lib/useLiveKline";

const DEFAULT_BOARDS: Record<AssetClass, string[]> = {
  crypto: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
  forex: ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
};
const storageKey = (cls: AssetClass) => `dp:watchlist:${cls}`;
const POLL_MS = 60_000;
// Forex watchlist sparklines are ambient, and Twelve Data's free tier is only
// 8 req/min — a fleet of tiles refreshing every 60s would starve the brief.
// Refresh them on a slow lane instead (the tile still shows a full 24h shape).
const FOREX_POLL_MS = 300_000;
const MAX_SYMBOLS = 8;
const TILE_INTERVAL = "1h"; // the sparkline is always a 24h/1h view

type TileData = { closes: number[]; last: string; changePct: number };

/** Base/quote split for display. Crypto is quoted in USDT; forex is two ISO
 *  codes (EURUSD → EUR / USD). */
function splitSymbol(symbol: string, cls: AssetClass): { base: string; quote: string } {
  if (cls === "forex") return { base: symbol.slice(0, 3), quote: `/${symbol.slice(3)}` };
  return { base: symbol.replace("USDT", ""), quote: "/USDT" };
}

function loadBoard(cls: AssetClass): string[] {
  const fallback = DEFAULT_BOARDS[cls];
  try {
    const raw = localStorage.getItem(storageKey(cls));
    if (!raw) return fallback;
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((s) => typeof s === "string") && parsed.length) {
      return parsed.slice(0, MAX_SYMBOLS);
    }
  } catch {
    /* corrupted storage → default */
  }
  return fallback;
}

function Sparkline({ closes, up }: { closes: number[]; up: boolean }) {
  const W = 84;
  const H = 30;
  if (closes.length < 2) return <svg width={W} height={H} />;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const pts = closes.map((c, i) => {
    const x = (i / (closes.length - 1)) * W;
    const y = H - 3 - ((c - min) / span) * (H - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const color = up ? "var(--bull)" : "var(--bear)";
  return (
    <svg width={W} height={H} aria-hidden="true">
      <defs>
        <linearGradient id={`sp-${up ? "u" : "d"}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`0,${H} ${pts.join(" ")} ${W},${H}`}
        fill={`url(#sp-${up ? "u" : "d"})`}
      />
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="1.2" opacity="0.9" />
    </svg>
  );
}

/** One tile's own WS subscription — a separate component so each symbol gets
 *  its own stable `useLiveKline` call (rules of hooks: the LIST of symbols
 *  can change, but each mounted tile's own hook count never does). Forex tiles
 *  pass `enabled=false` — there is no free real-time forex WS, so the 60s REST
 *  poll is their only price source. */
function WatchlistTile({
  symbol,
  assetClass,
  active,
  data,
  onSelect,
  onRemove,
}: {
  symbol: string;
  assetClass: AssetClass;
  active: boolean;
  data: TileData | undefined;
  onSelect: (s: string) => void;
  onRemove: (() => void) | null;
}) {
  const { liveTick } = useLiveKline(symbol, TILE_INTERVAL, assetClass === "crypto");

  const liveLast = liveTick?.close ?? data?.last;
  // Approximate the still-forming bar: swap in the live close as the last
  // point. Precisely tracking the hour boundary isn't worth the complexity
  // here (unlike the main chart) — the next 60s REST poll rebuilds the whole
  // array fresh and self-corrects around any rollover.
  const liveCloses =
    data && liveTick
      ? [...data.closes.slice(0, -1), parseFloat(liveTick.close)]
      : data?.closes;
  const liveChangePct =
    data && liveCloses && liveCloses[0]
      ? ((liveCloses[liveCloses.length - 1] - liveCloses[0]) / liveCloses[0]) * 100
      : data?.changePct;

  const up = (liveChangePct ?? 0) >= 0;
  const { base, quote } = splitSymbol(symbol, assetClass);

  return (
    <div className={`wl-tile group relative border-l-2 ${active ? "wl-active border-l-pulse" : "border-l-transparent"}`}>
      <button
        onClick={() => onSelect(symbol)}
        className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left"
      >
        <div className="min-w-0">
          <div className="font-mono text-[12px] tracking-wide text-hi">
            {base}
            <span className="text-dim">{quote}</span>
          </div>
          {data ? (
            <>
              <div className="mt-0.5 font-mono text-[13px] font-light tabular-nums text-mid">
                {liveLast ? formatPrice(liveLast) : "—"}
              </div>
              <div className={`font-mono text-[10px] tabular-nums ${up ? "text-bull" : "text-bear"}`}>
                {up ? "+" : ""}
                {(liveChangePct ?? 0).toFixed(2)}% · 24h
              </div>
            </>
          ) : (
            <div className="mt-0.5 font-mono text-[11px] text-dim">— — —</div>
          )}
        </div>
        {liveCloses && <Sparkline closes={liveCloses} up={up} />}
      </button>
      {onRemove && (
        <button
          onClick={onRemove}
          className="absolute top-1.5 right-2 font-mono text-[11px] text-dim opacity-0 transition-opacity duration-150 group-hover:opacity-100 hover:text-bear"
          title={`remove ${symbol} · তালিকা থেকে বাদ`}
          aria-label={`remove ${symbol} from watchlist`}
        >
          ×
        </button>
      )}
    </div>
  );
}

/* Home() re-renders every 15s (klines) / 30s (brief) poll; this rail's own
   props (active symbol, a stable onSelect callback) don't change on those
   ticks, so memo skips needless reconciliation of its ~8 tiles + sparklines.
   The parent passes key={assetClass}, so a class switch remounts the rail
   with a fresh per-class board rather than mutating this instance. */
function WatchlistRail({
  active,
  assetClass,
  onSelect,
}: {
  active: string;
  assetClass: AssetClass;
  onSelect: (symbol: string) => void;
}) {
  const [board, setBoard] = useState<string[]>(() => DEFAULT_BOARDS[assetClass]);
  const [tiles, setTiles] = useState<Record<string, TileData>>({});
  const [draft, setDraft] = useState("");

  // hydrate from localStorage after mount (SSR-safe), then push it to the
  // backend once so the background scanner (Active mode, P3) knows what to
  // watch even before the user adds/removes anything this session.
  useEffect(() => {
    const loaded = loadBoard(assetClass);
    setBoard(loaded);
    syncWatchlist(loaded).catch(() => {}); // best-effort — desk works offline
  }, [assetClass]);

  const persist = useCallback(
    (next: string[]) => {
      setBoard(next);
      try {
        localStorage.setItem(storageKey(assetClass), JSON.stringify(next));
      } catch {
        /* storage full/blocked — board still works in-memory */
      }
      syncWatchlist(next).catch(() => {}); // mirror to the scanner's watchlist
    },
    [assetClass],
  );

  const addSymbol = () => {
    const s = draft.trim().toUpperCase();
    if (!s) return;
    let symbol = s;
    if (assetClass === "crypto") {
      // Typing "DOGE" is enough — everything on the crypto board is USDT-quoted.
      if (!symbol.endsWith("USDT") && /^[A-Z0-9]{2,12}$/.test(symbol)) symbol = `${symbol}USDT`;
      if (!/^[A-Z0-9]{5,20}$/.test(symbol)) return;
    } else {
      // Forex needs a full 6-letter pair (e.g. GBPJPY); no auto-suffix.
      if (!/^[A-Z]{6}$/.test(symbol)) return;
    }
    if (board.includes(symbol) || board.length >= MAX_SYMBOLS) return;
    persist([...board, symbol]);
    setDraft("");
  };

  const canAdd = draft.trim().length > 0;

  const removeSymbol = (s: string) => {
    if (board.length <= 1) return; // never empty the board
    persist(board.filter((b) => b !== s));
  };

  const poll = useCallback(async () => {
    const results = await Promise.allSettled(board.map((s) => fetchKlines(s, TILE_INTERVAL, 25)));
    setTiles((prev) => {
      const next = { ...prev };
      results.forEach((r, i) => {
        if (r.status !== "fulfilled" || r.value.length < 2) return;
        const ks: Kline[] = r.value;
        const closes = ks.map((k) => parseFloat(k.close)); // display-only
        const first = closes[0];
        const last = closes[closes.length - 1];
        next[board[i]] = {
          closes,
          last: ks[ks.length - 1].close,
          changePct: first ? ((last - first) / first) * 100 : 0,
        };
      });
      return next;
    });
  }, [board]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, assetClass === "forex" ? FOREX_POLL_MS : POLL_MS);
    return () => clearInterval(id);
  }, [poll, assetClass]);

  const addPlaceholder = assetClass === "forex" ? "e.g. GBPJPY · পেয়ার যোগ করুন" : "e.g. DOGE · কয়েন যোগ করুন";

  return (
    <div className="card dp-rise flex shrink-0 flex-col" style={{ animationDelay: "100ms" }}>
      <div className="flex items-start justify-between gap-2 border-b border-hair/70 px-4 py-2.5">
        <span className="min-w-0">
          <span className="flex items-center gap-1.5">
            <Term k="WATCHLIST" className="micro-label block">watchlist</Term>
            <SourceBadge surface="watchlist" />
          </span>
          <span className="bn-sub mt-0.5">নজর তালিকা</span>
        </span>
        <span className="live-dot mt-1 bg-bull" />
      </div>
      <div className="flex flex-col divide-y divide-hair/40">
        {board.map((s) => (
          <WatchlistTile
            key={s}
            symbol={s}
            assetClass={assetClass}
            active={s === active}
            data={tiles[s]}
            onSelect={onSelect}
            onRemove={board.length > 1 ? () => removeSymbol(s) : null}
          />
        ))}
      </div>
      {board.length < MAX_SYMBOLS && (
        <form
          className="flex items-center gap-2 border-t border-hair/50 px-3 py-2"
          onSubmit={(e) => {
            e.preventDefault();
            addSymbol();
          }}
        >
          <span className="font-mono text-[11px] text-dim">+</span>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            placeholder={addPlaceholder}
            spellCheck={false}
            className="min-w-0 flex-1 bg-transparent font-mono text-[11px] tracking-wide text-hi outline-none placeholder:text-dim/70"
            aria-label="add symbol to watchlist"
          />
          <button
            type="submit"
            disabled={!canAdd}
            className="shrink-0 rounded-md border border-hair px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-mid transition-colors duration-150 hover:border-pulse/40 hover:text-hi disabled:opacity-40"
            aria-label="add"
          >
            <span className="font-bn">যোগ</span> add
          </button>
        </form>
      )}
    </div>
  );
}

export default memo(WatchlistRail);
