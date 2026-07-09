"use client";

/** DARKPOOL analysis view — premium pass (ADR-0011).
 *  Deterministic engine output only: data colors (teal/red/amber).
 *  Gold stays reserved for the AI layer arriving in P2. */

import { useCallback, useEffect, useRef, useState } from "react";

import Clock from "@/components/Clock";
import CommandPalette from "@/components/CommandPalette";
import DeskNav from "@/components/DeskNav";
import DeskTape from "@/components/DeskTape";
import DeskVerdict from "@/components/DeskVerdict";
import FearGreedDial from "@/components/FearGreedDial";
import FullDeskPanel from "@/components/FullDeskPanel";
import PipelineMap from "@/components/PipelineMap";
import PriceChart from "@/components/PriceChart";
import SetupShelf from "@/components/SetupShelf";
import SignalReadout from "@/components/SignalReadout";
import Term from "@/components/Term";
import WatchlistRail from "@/components/WatchlistRail";
import {
  fetchBrief,
  fetchDesk,
  fetchKlines,
  fetchQuickRead,
  fetchScannerMode,
  formatPrice,
  type DeskPanelResponse,
  type Kline,
  type MarketBrief,
  type QuickReadResponse,
  type ScannerMode,
  type TimeframeAnalysis,
} from "@/lib/api";
import { biasKey, trendKey } from "@/lib/terms";
import { dhakaTime } from "@/lib/time";
import { useLiveKline } from "@/lib/useLiveKline";

const TFS = ["5m", "15m", "1h", "4h", "1d"] as const;
type TF = (typeof TFS)[number];
// The WebSocket stream (P3) is now the primary path for price/chart updates —
// this poll is a slow safety net (resync if a tab was asleep, WS briefly
// down) rather than the main data path, hence the relaxed interval.
const KLINES_MS = 45_000;
const BRIEF_MS = 30_000;
const SCAN_MODE_MS = 20_000;

const trendColor = (t?: string) =>
  t === "bullish" ? "text-bull" : t === "bearish" ? "text-bear" : "text-mid";

/* ── Living details ──────────────────────────────────────────────────────── */

/** Price odometer — changed digits remount and roll in tick-direction. */
function Odometer({ text, direction }: { text: string; direction: "up" | "down" | "flat" }) {
  const anim = direction === "up" ? "digit-up" : direction === "down" ? "digit-down" : "";
  return (
    <span aria-label={text}>
      {text.split("").map((ch, i) => (
        <span key={`${i}-${ch}`} className={`digit ${anim}`}>
          {ch}
        </span>
      ))}
    </span>
  );
}

function SegTabs({ value, onChange }: { value: TF; onChange: (t: TF) => void }) {
  const idx = TFS.indexOf(value);
  return (
    <div className="relative flex rounded-lg border border-hair bg-abyss/60 p-0.5">
      <span
        className="absolute top-0.5 bottom-0.5 left-0.5 rounded-md bg-raised"
        style={{
          width: `calc((100% - 4px) / ${TFS.length})`,
          transform: `translateX(${idx * 100}%)`,
          transition: "transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        }}
      />
      {TFS.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`relative z-10 w-10 py-1 text-center font-mono text-[11px] transition-colors duration-200 sm:w-12 sm:text-xs ${
            t === value ? "text-hi" : "text-dim hover:text-mid"
          }`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

/** Card header — English micro-label with the Bengali name stacked directly
 *  under it. Stacking (not beside) guarantees the Bengali is never truncated,
 *  whatever the card width (root-cause fix for the clipped "বিশ্লেষকদের ঐক…"). */
function CardHeader({ children, bn, right }: { children: React.ReactNode; bn?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-hair/70 px-5 py-2.5">
      <span className="min-w-0">
        <span className="micro-label block">{children}</span>
        {bn && <span className="bn-sub mt-0.5">{bn}</span>}
      </span>
      {right && <span className="shrink-0">{right}</span>}
    </div>
  );
}

/* ── Page ────────────────────────────────────────────────────────────────── */

export default function Home() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [draft, setDraft] = useState("BTCUSDT");
  const [tf, setTf] = useState<TF>("1h");
  const [candles, setCandles] = useState<Kline[]>([]);
  const [brief, setBrief] = useState<MarketBrief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [dir, setDir] = useState<"up" | "down" | "flat">("flat");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [quickRead, setQuickRead] = useState<QuickReadResponse | null>(null);
  const [qrRunning, setQrRunning] = useState(false);
  const [deskOpen, setDeskOpen] = useState(false);
  const [deskData, setDeskData] = useState<DeskPanelResponse | null>(null);
  const [deskRunning, setDeskRunning] = useState(false);
  const [scanMode, setScanMode] = useState<ScannerMode | null>(null);
  const prevClose = useRef<number | null>(null);
  const briefSymbol = useRef<string>("");

  // Live price stream (P3) — the primary path; REST above is now the backfill
  // + slow safety-net poll. `liveTick` updates as fast as trades arrive.
  const { liveTick, connected: wsConnected } = useLiveKline(symbol, tf);

  // One Quick Read per symbol (60s server cache); ⟳ forces a fresh run.
  const runQuickRead = useCallback(
    async (force = false) => {
      setQrRunning(true);
      try {
        setQuickRead(await fetchQuickRead(symbol, force));
      } catch {
        setQuickRead(null); // 503 = no key configured → card stays in demo mode
      } finally {
        setQrRunning(false);
      }
    },
    [symbol],
  );

  useEffect(() => {
    setQuickRead(null);
    runQuickRead();
  }, [runQuickRead]);

  // Full Desk (tier 2) — fans out 4 analysts; server-cached 120s so re-opening
  // is cheap. Reset when the symbol changes so a stale panel never lingers.
  const runDesk = useCallback(
    async (force = false) => {
      setDeskRunning(true);
      try {
        setDeskData(await fetchDesk(symbol, force));
      } catch {
        setDeskData(null); // 503 (no panel) / network → overlay shows a retry state
      } finally {
        setDeskRunning(false);
      }
    },
    [symbol],
  );
  const openDesk = useCallback(() => {
    setDeskOpen(true);
    runDesk();
  }, [runDesk]);
  useEffect(() => {
    setDeskData(null);
  }, [symbol]);

  const retarget = useCallback((s: string) => {
    setSymbol(s);
    setDraft(s);
  }, []);

  // Ctrl+K / ⌘K summons the palette from anywhere (C4 signature #7)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const pollKlines = useCallback(async () => {
    const t0 = performance.now();
    try {
      const data = await fetchKlines(symbol, tf);
      const numeric = data.length ? Number(data[data.length - 1].close) : null; // direction only
      if (numeric !== null && prevClose.current !== null && numeric !== prevClose.current) {
        setDir(numeric > prevClose.current ? "up" : "down");
      }
      prevClose.current = numeric;
      setCandles(data);
      setLatency(Math.round(performance.now() - t0));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "fetch failed");
    }
  }, [symbol, tf]);

  const pollBrief = useCallback(async () => {
    try {
      const data = await fetchBrief(symbol);
      briefSymbol.current = data.symbol;
      setBrief(data);
    } catch {
      /* brief is enrichment; kline errors already surface */
    }
  }, [symbol]);

  useEffect(() => {
    prevClose.current = null;
    setDir("flat");
    pollKlines();
    const id = setInterval(pollKlines, KLINES_MS);
    return () => clearInterval(id);
  }, [pollKlines]);

  // Apply each live tick: same bar → just move the ticker/direction (the
  // chart's own cheap `.update()` path handles the visual, via the `liveTick`
  // prop below); a NEW bar → append it so the REST-shaped `candles` array
  // (and the chart's full-reload path) stays correct once the bar closes.
  useEffect(() => {
    if (!liveTick) return;
    const numeric = Number(liveTick.close);
    if (prevClose.current !== null && numeric !== prevClose.current) {
      setDir(numeric > prevClose.current ? "up" : "down");
    }
    prevClose.current = numeric;

    setCandles((prev) => {
      if (!prev.length) return prev; // wait for the initial REST backfill
      const last = prev[prev.length - 1];
      if (last.open_time === liveTick.open_time) return prev; // same forming bar
      return [...prev.slice(1), liveTick]; // bar rolled over — append, drop oldest
    });
  }, [liveTick]);

  useEffect(() => {
    pollBrief();
    const id = setInterval(pollBrief, BRIEF_MS);
    return () => clearInterval(id);
  }, [pollBrief]);

  // Scanner mode (P3) — read-only mirror of the Settings toggle, so switching
  // to Active there is reflected here without a page reload.
  useEffect(() => {
    const poll = () => fetchScannerMode().then((r) => setScanMode(r.mode)).catch(() => {});
    poll();
    const id = setInterval(poll, SCAN_MODE_MS);
    return () => clearInterval(id);
  }, []);

  const briefReady = brief && briefSymbol.current === symbol ? brief : null;
  const tfa: TimeframeAnalysis | undefined = briefReady?.timeframes[tf];
  const lastClose = liveTick?.close ?? (candles.length ? candles[candles.length - 1].close : null);
  const alignment = briefReady?.alignment;
  const hero =
    alignment && Math.abs(alignment.score) >= 0.99
      ? alignment.bias === "long"
        ? "hero-long hero-sheen"
        : "hero-short hero-sheen"
      : "";
  const levels = [...(briefReady?.daily_levels ?? []), ...(tfa?.equal_levels ?? [])];
  const priceColor = dir === "up" ? "text-bull" : dir === "down" ? "text-bear" : "text-hi";
  const live = candles.length > 0 && error === null;

  return (
    <main className="desk-lock flex min-h-screen flex-col">
      <div
        className={`stage flex min-h-0 flex-1 flex-col ${paletteOpen ? "stage-recede" : ""}`}
      >
      {/* ── Command bar ── */}
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-2.5 border-b border-hair/80 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-5">
          <div className="flex items-baseline gap-2.5">
            <span className="text-[13px] font-semibold tracking-[0.42em] text-hi">DARKPOOL</span>
            <span className="hidden text-[12px] font-semibold tracking-[0.08em] text-gold sm:inline">desk</span>
          </div>
          <DeskNav />
        </div>
        <form
          className="order-last flex w-full items-center overflow-hidden rounded-lg border border-hair bg-abyss/70 focus-within:border-dim md:order-none md:w-auto"
          onSubmit={(e) => {
            e.preventDefault();
            const s = draft.trim().toUpperCase();
            if (/^[A-Z0-9]{5,20}$/.test(s)) setSymbol(s);
          }}
        >
          <span className="pl-3 font-mono text-xs text-gold">▸</span>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            spellCheck={false}
            className="w-full flex-1 bg-transparent px-2.5 py-2 font-mono text-sm tracking-wide text-hi outline-none placeholder:text-dim md:w-44 md:flex-none"
            placeholder="SYMBOL"
            aria-label="symbol"
          />
          <button
            type="submit"
            className="border-l border-hair px-3.5 py-2 text-[11px] font-medium uppercase tracking-[0.14em] text-mid transition-colors duration-200 hover:bg-raised hover:text-hi"
          >
            analyze
          </button>
        </form>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setPaletteOpen(true)}
            className="chip hidden !py-1 transition-colors duration-200 hover:text-hi md:inline-flex"
            title="command palette"
          >
            ⌘K
          </button>
          <span className={`live-dot ${live ? "bg-bull" : "bg-bear"}`} />
          <Clock />
        </div>
      </header>

      {/* ── Ticker strip ── */}
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3 px-4 pt-5 pb-3 sm:px-6">
        <div>
          <div className="micro-label mb-1.5 flex items-center gap-2">
            {symbol} · spot · binance
            <span
              className={`live-dot ${wsConnected ? "bg-pulse" : "bg-raised"}`}
              title={wsConnected ? "live · websocket" : "reconnecting…"}
            />
          </div>
          <div className={`font-mono text-4xl font-light leading-none tabular-nums sm:text-5xl ${priceColor}`}>
            {lastClose ? <Odometer text={formatPrice(lastClose)} direction={dir} /> : "— — —"}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 pb-1">
          {tfa && (
            <>
              <span className="chip">
                <span className={trendColor(tfa.structure.trend)}>
                  {tfa.structure.trend === "bullish" ? "▲" : tfa.structure.trend === "bearish" ? "▼" : "◆"}
                </span>
                <Term k={trendKey(tfa.structure.trend)}>{tfa.structure.trend}</Term>
              </span>
              <span className="chip">
                <Term k="PREMIUM_DISCOUNT" below>{tfa.premium_discount}</Term>
              </span>
            </>
          )}
          {alignment && (
            <span className="chip">
              <Term k="MTF" below>mtf</Term>{" "}
              <span className={trendColor(alignment.bias === "long" ? "bullish" : alignment.bias === "short" ? "bearish" : "range")}>
                {alignment.score > 0 ? "+" : ""}
                {alignment.score.toFixed(2)}
              </span>
            </span>
          )}
        </div>
      </div>

      {/* ── Stage ── */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 px-4 pb-4 sm:px-6 lg:flex-row">
        {/* Board rail — watchlist tiles + desk tape. Stacks last on mobile;
            hidden only in the tight lg–xl band to protect chart width. */}
        <aside className="order-3 flex w-full shrink-0 flex-col gap-3.5 lg:hidden xl:order-none xl:flex xl:w-[248px]">
          <WatchlistRail active={symbol} onSelect={retarget} />
          <DeskTape symbol={symbol} />
        </aside>

        {/* Center column — chart stage + setups shelf */}
        <div className="order-1 flex min-h-0 min-w-0 flex-1 flex-col gap-4 xl:order-none">
        {/* Chart gets a fixed, consistent height (no fullscreen stretch); the
            setups shelf below fills the remaining column space and scrolls. */}
        <section className="card hud-corners glow-live dp-rise flex h-[380px] min-w-0 flex-col overflow-hidden lg:h-[clamp(360px,50vh,560px)]">
          <div className="flex items-center justify-between border-b border-hair/70 px-5 py-3">
            <div className="flex items-center gap-3">
              <span className="micro-label">price · {tf}</span>
              {tfa?.structure.last_event && (
                <span className="chip">
                  <Term k={tfa.structure.last_event.kind === "BOS" ? "BOS" : "CHOCH"} below>
                    <span className={tfa.structure.last_event.direction === "bullish" ? "text-bull" : "text-bear"}>
                      {tfa.structure.last_event.kind}
                    </span>
                  </Term>
                  @ {formatPrice(tfa.structure.last_event.level)}
                </span>
              )}
            </div>
            <SegTabs value={tf} onChange={setTf} />
          </div>
          <SignalReadout tfa={tfa} levels={levels} price={lastClose ? parseFloat(lastClose) : null} />
          <div className="relative min-h-0 flex-1">
            <PriceChart candles={candles} levels={levels} lastEvent={tfa?.structure.last_event ?? null} liveTick={liveTick} />
          </div>
        </section>

        {/* Setup variants across Binance venues (FR-4) */}
        <SetupShelf symbol={symbol} price={lastClose ? parseFloat(lastClose) : null} />
        </div>

        {/* Desk rail */}
        <aside className="order-2 flex w-full shrink-0 flex-col gap-3.5 [overflow-anchor:none] *:shrink-0 lg:w-[372px] lg:overflow-y-auto lg:pr-0.5 xl:order-none">
          {/* The AI layer — gold, and only here (ADR-0010) */}
          <DeskVerdict
            symbol={symbol}
            price={lastClose ? parseFloat(lastClose) : null}
            data={quickRead}
            running={qrRunning}
            onRun={() => runQuickRead(true)}
          />
          <PipelineMap panel={deskData} onOpenDesk={openDesk} />

          {/* Alignment — the engine's verdict moment */}
          <div className={`card dp-rise px-5 py-4 ${hero}`} style={{ animationDelay: "120ms" }}>
            <div className="min-w-0">
              <Term k="MTF" className="micro-label">mtf alignment · engine</Term>
              <span className="bn-sub mt-0.5">টাইমফ্রেম ঐক্য · সব চার্ট এক দিকে?</span>
            </div>
            {alignment ? (
              <>
                <div className="mt-2 flex items-baseline justify-between">
                  <span
                    className={`text-[30px] font-bold leading-none tracking-tight ${
                      alignment.bias === "long" ? "text-bull" : alignment.bias === "short" ? "text-bear" : "text-mid"
                    }`}
                  >
                    <Term k={biasKey(alignment.bias)}>
                      {alignment.bias === "mixed" ? "Mixed" : alignment.bias === "long" ? "Long bias" : "Short bias"}
                    </Term>
                  </span>
                  <span className="font-mono text-sm tabular-nums text-mid">
                    {alignment.score > 0 ? "+" : ""}
                    {alignment.score.toFixed(2)}
                  </span>
                </div>
                <div className="mt-3.5 flex gap-1.5">
                  {Object.entries(alignment.per_tf).map(([k, v]) => (
                    <div key={k} className="flex-1">
                      <div
                        className={`h-[3px] rounded-full ${
                          v === "bullish" ? "bg-bull" : v === "bearish" ? "bg-bear" : "bg-raised"
                        }`}
                        style={{ opacity: v === "range" ? 0.6 : 0.9 }}
                      />
                      <div className="mt-1.5 text-center font-mono text-[10px] text-dim">{k}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="mt-2 text-sm text-dim">calibrating…</div>
            )}
          </div>

          {/* Structure */}
          <div className="card dp-rise" style={{ animationDelay: "180ms" }}>
            <CardHeader bn="বাজার কাঠামো">
              <Term k="STRUCTURE" below>structure</Term>
            </CardHeader>
            <div className="divide-y divide-hair/50 px-5">
              {briefReady ? (
                Object.values(briefReady.timeframes).map((t) => (
                  <div key={t.tf} className="grid grid-cols-[42px_84px_1fr_auto] items-center gap-2 py-3">
                    <span className="font-mono text-[11px] text-dim">{t.tf}</span>
                    <span className={`text-[13px] font-medium ${trendColor(t.structure.trend)}`}>
                      {t.structure.trend === "bullish" ? "▲ " : t.structure.trend === "bearish" ? "▼ " : "◆ "}
                      <Term k={trendKey(t.structure.trend)}>{t.structure.trend}</Term>
                    </span>
                    <span className="text-right font-mono text-[11px] tabular-nums text-mid">
                      {t.structure.last_event ? (
                        <>
                          <Term k={t.structure.last_event.kind === "BOS" ? "BOS" : "CHOCH"}>
                            {t.structure.last_event.kind}
                          </Term>{" "}
                          @ {formatPrice(t.structure.last_event.level)}
                        </>
                      ) : (
                        "—"
                      )}
                    </span>
                    <span className="w-16 text-right font-mono text-[10px] text-dim">
                      <Term k="PREMIUM_DISCOUNT">{t.premium_discount}</Term>
                    </span>
                  </div>
                ))
              ) : (
                <div className="py-3 text-sm text-dim">calibrating…</div>
              )}
            </div>
          </div>

          {/* Derivatives */}
          <div className="card dp-rise" style={{ animationDelay: "240ms" }}>
            <CardHeader bn="ডেরিভেটিভস ডেটা">
              <Term k="PERP" below>derivatives · usdⓈ-m perp</Term>
            </CardHeader>
            {briefReady?.derivatives ? (
              <div className="grid grid-cols-3 divide-x divide-hair/50">
                <div className="px-4 py-3.5 text-center">
                  <div
                    className={`font-mono text-[15px] font-light tabular-nums ${
                      briefReady.derivatives.funding_regime === "neutral"
                        ? "text-hi"
                        : briefReady.derivatives.funding_regime.endsWith("extreme")
                          ? "text-bear"
                          : "text-warn"
                    }`}
                  >
                    {(briefReady.derivatives.funding_rate * 100).toFixed(4)}%
                  </div>
                  <div className="micro-label mt-1.5">
                    <Term k="FUNDING">funding</Term>
                  </div>
                </div>
                <div className="px-4 py-3.5 text-center">
                  <div
                    className={`font-mono text-[15px] font-light tabular-nums ${
                      (briefReady.derivatives.oi_change_24h_pct ?? 0) >= 0 ? "text-bull" : "text-bear"
                    }`}
                  >
                    {briefReady.derivatives.oi_change_24h_pct != null
                      ? `${briefReady.derivatives.oi_change_24h_pct >= 0 ? "+" : ""}${briefReady.derivatives.oi_change_24h_pct.toFixed(2)}%`
                      : "—"}
                  </div>
                  <div className="micro-label mt-1.5">
                    <Term k="OI">oi Δ 24h</Term>
                  </div>
                </div>
                <div className="px-4 py-3.5 text-center">
                  <div className="font-mono text-[15px] font-light tabular-nums text-hi">
                    {briefReady.derivatives.long_short_ratio?.toFixed(2) ?? "—"}
                  </div>
                  <div className="micro-label mt-1.5">
                    <Term k="LS_RATIO">long / short</Term>
                  </div>
                </div>
              </div>
            ) : (
              <div className="px-5 py-3.5 text-sm text-dim">{briefReady ? "no futures market" : "calibrating…"}</div>
            )}
          </div>

          {/* Sentiment */}
          <div className="card dp-rise" style={{ animationDelay: "300ms" }}>
            <CardHeader bn="বাজারের মেজাজ">
              <Term k="FNG" below>sentiment · fear & greed</Term>
            </CardHeader>
            <div className="px-5 py-4">
              {briefReady?.sentiment ? (
                <FearGreedDial value={briefReady.sentiment.fear_greed} label={briefReady.sentiment.label} />
              ) : (
                <div className="text-sm text-dim">calibrating…</div>
              )}
            </div>
          </div>

          {/* Zones & liquidity */}
          <div className="card dp-rise" style={{ animationDelay: "360ms" }}>
            <CardHeader bn="জোন ও লিকুইডিটি">
              <Term k="LIQUIDITY" below>zones & liquidity · {tf}</Term>
            </CardHeader>
            <div className="space-y-2.5 px-5 py-4">
              {tfa ? (
                <>
                  {[...tfa.order_blocks, ...tfa.fvgs].map((z, i) => (
                    <div key={i} className="flex items-center text-xs">
                      <span
                        className={`mr-2.5 h-3.5 w-[2.5px] rounded-full ${z.side === "bullish" ? "bg-bull" : "bg-bear"}`}
                      />
                      <span className="w-9 font-mono text-mid">
                        <Term k={z.kind === "order_block" ? "OB" : "FVG"}>
                          {z.kind === "order_block" ? "OB" : "FVG"}
                        </Term>
                      </span>
                      <span className="leader" />
                      <span className="font-mono tabular-nums text-hi">
                        {formatPrice(z.bottom)} <span className="text-dim">–</span> {formatPrice(z.top)}
                      </span>
                      <span className={`ml-3 w-14 text-right font-mono text-[10px] ${z.mitigated ? "text-dim" : "text-pulse"}`}>
                        <Term k={z.mitigated ? "MITIGATED" : "FRESH"} edge>
                          {z.mitigated ? "mitigated" : "fresh"}
                        </Term>
                      </span>
                    </div>
                  ))}
                  {levels.map((lv, i) => (
                    <div key={`l${i}`} className="flex items-center text-xs">
                      <span className="mr-2.5 h-3.5 w-[2.5px] rounded-full bg-warn/80" />
                      <span className="w-9 font-mono text-warn">
                        <Term k={lv.kind}>{lv.kind}</Term>
                      </span>
                      <span className="leader" />
                      <span className="font-mono tabular-nums text-hi">{formatPrice(lv.price)}</span>
                      <span
                        className={`ml-3 w-14 text-right font-mono text-[10px] ${
                          lv.state === "intact" ? "text-pulse" : "text-dim"
                        }`}
                      >
                        {lv.state === "swept" ? <Term k="SWEPT" edge>swept</Term> : lv.state}
                      </span>
                    </div>
                  ))}
                  {tfa.order_blocks.length + tfa.fvgs.length + levels.length === 0 && (
                    <div className="text-xs text-dim">nothing detected</div>
                  )}
                </>
              ) : (
                <div className="text-xs text-dim">calibrating…</div>
              )}
            </div>
          </div>
        </aside>
      </div>

      {/* ── Status line ── */}
      <footer className="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-hair/80 px-4 py-2 text-[11px] text-dim sm:px-6">
        <span className="flex items-center gap-2">
          <span className={`live-dot ${live ? "bg-bull" : "bg-bear"}`} />
          binance · public data · keyless
          {error ? <span className="text-bear"> · {error}</span> : null}
          {scanMode && (
            <span className={scanMode === "active" ? "text-warn" : "text-dim"}>
              · scan: {scanMode}
              {scanMode === "active" && <span className="live-dot ml-1.5 bg-warn" />}
            </span>
          )}
        </span>
        <span className="font-mono tabular-nums">
          {briefReady ? `brief ${dhakaTime(briefReady.generated_at)} · ` : ""}
          {latency !== null ? `api ${latency}ms` : "api —"} · llm $0.00 · v0.1
        </span>
      </footer>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={retarget}
      />

      <FullDeskPanel
        open={deskOpen}
        onClose={() => setDeskOpen(false)}
        symbol={symbol}
        data={deskData}
        running={deskRunning}
        onRun={() => runDesk(true)}
      />
    </main>
  );
}
