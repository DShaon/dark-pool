"use client";

/** Watchlist rail (ADR-0011: sparkline tiles). LIVE PRICE (P3): each tile now
 *  carries its own WebSocket tick (same `BinanceStreamHub` the main chart
 *  uses — the backend already shares one upstream Binance subscription per
 *  symbol+interval across every local subscriber, so watching a symbol here
 *  AND on the main chart costs nothing extra upstream). REST still refreshes
 *  the 24h sparkline shape every 60s; the live tick moves the price, the 24h
 *  change%, and the sparkline's last point in between polls.
 *
 *  The board persists in localStorage (single-user P1; server-side
 *  persistence arrives with the DB). Add via the input, remove via ×.
 */

import { memo, useCallback, useEffect, useState } from "react";

import Term from "@/components/Term";
import { fetchKlines, formatPrice, syncWatchlist, type Kline } from "@/lib/api";
import { useLiveKline } from "@/lib/useLiveKline";

const DEFAULT_BOARD = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
const STORAGE_KEY = "dp:watchlist";
const POLL_MS = 60_000;
const MAX_SYMBOLS = 8;
const TILE_INTERVAL = "1h"; // the sparkline is always a 24h/1h view

type TileData = { closes: number[]; last: string; changePct: number };

function loadBoard(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_BOARD;
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((s) => typeof s === "string") && parsed.length) {
      return parsed.slice(0, MAX_SYMBOLS);
    }
  } catch {
    /* corrupted storage → default */
  }
  return DEFAULT_BOARD;
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
 *  can change, but each mounted tile's own hook count never does). */
function WatchlistTile({
  symbol,
  active,
  data,
  onSelect,
  onRemove,
}: {
  symbol: string;
  active: boolean;
  data: TileData | undefined;
  onSelect: (s: string) => void;
  onRemove: (() => void) | null;
}) {
  const { liveTick } = useLiveKline(symbol, TILE_INTERVAL);

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

  return (
    <div className={`wl-tile group relative border-l-2 ${active ? "wl-active border-l-pulse" : "border-l-transparent"}`}>
      <button
        onClick={() => onSelect(symbol)}
        className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left"
      >
        <div className="min-w-0">
          <div className="font-mono text-[12px] tracking-wide text-hi">
            {symbol.replace("USDT", "")}
            <span className="text-dim">/USDT</span>
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
   ticks, so memo skips needless reconciliation of its ~8 tiles + sparklines. */
function WatchlistRail({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (symbol: string) => void;
}) {
  const [board, setBoard] = useState<string[]>(DEFAULT_BOARD);
  const [tiles, setTiles] = useState<Record<string, TileData>>({});
  const [draft, setDraft] = useState("");

  // hydrate from localStorage after mount (SSR-safe), then push it to the
  // backend once so the background scanner (Active mode, P3) knows what to
  // watch even before the user adds/removes anything this session.
  useEffect(() => {
    const loaded = loadBoard();
    setBoard(loaded);
    syncWatchlist(loaded).catch(() => {}); // best-effort — desk works offline
  }, []);

  const persist = useCallback((next: string[]) => {
    setBoard(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* storage full/blocked — board still works in-memory */
    }
    syncWatchlist(next).catch(() => {}); // mirror to the scanner's watchlist
  }, []);

  const addSymbol = () => {
    let s = draft.trim().toUpperCase();
    if (!s) return;
    // Typing "DOGE" is enough — everything on the board is quoted in USDT.
    if (!s.endsWith("USDT") && /^[A-Z0-9]{2,12}$/.test(s)) s = `${s}USDT`;
    if (!/^[A-Z0-9]{5,20}$/.test(s) || board.includes(s) || board.length >= MAX_SYMBOLS) return;
    persist([...board, s]);
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
    const id = setInterval(poll, POLL_MS);
    return () => clearInterval(id);
  }, [poll]);

  return (
    <div className="card dp-rise flex shrink-0 flex-col" style={{ animationDelay: "100ms" }}>
      <div className="flex items-start justify-between gap-2 border-b border-hair/70 px-4 py-2.5">
        <span className="min-w-0">
          <Term k="WATCHLIST" className="micro-label block">watchlist</Term>
          <span className="bn-sub mt-0.5">নজর তালিকা</span>
        </span>
        <span className="live-dot mt-1 bg-bull" />
      </div>
      <div className="flex flex-col divide-y divide-hair/40">
        {board.map((s) => (
          <WatchlistTile
            key={s}
            symbol={s}
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
            placeholder="e.g. DOGE · কয়েন যোগ করুন"
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
