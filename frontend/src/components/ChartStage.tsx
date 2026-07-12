"use client";

/** Chart stage (ADR-0017) — the candle chart plus its toolbar: draw a chosen
 *  plan (entry/SL/TP + a future path), toggle OB/FVG zone bands, toggle the AI
 *  scenario path (gold, "sequence opinion, not a forecast"), jump to any waiting
 *  liquidity level, and refresh. Everything drawn comes from data already on
 *  screen or a named endpoint — no invented numbers (invariant 7).
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import PriceChart, { type ChartPlan, type ChartScenario } from "@/components/PriceChart";
import SegTabs, { type TF } from "@/components/SegTabs";
import SignalReadout from "@/components/SignalReadout";
import SourceBadge from "@/components/SourceBadge";
import Term from "@/components/Term";
import {
  fetchPlan,
  fetchQuickRead,
  fetchScenario,
  formatPrice,
  type Kline,
  type LevelOut,
  type TimeframeAnalysis,
} from "@/lib/api";

type PlanSource = "quickread" | "cio";

function ToolButton({
  on,
  onClick,
  gold = false,
  title,
  children,
}: {
  on: boolean;
  onClick: () => void;
  gold?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`rounded-md border px-2 py-[3px] font-mono text-[10px] uppercase tracking-[0.1em] transition-colors duration-150 ${
        on
          ? gold
            ? "border-gold/50 text-gold"
            : "border-pulse/50 text-hi"
          : "border-hair text-dim hover:text-mid"
      }`}
    >
      {children}
    </button>
  );
}

export default function ChartStage({
  symbol,
  tf,
  setTf,
  tfa,
  levels,
  candles,
  liveTick,
  lastClose,
  onRefresh,
}: {
  symbol: string;
  tf: TF;
  setTf: (t: TF) => void;
  tfa?: TimeframeAnalysis;
  levels: LevelOut[];
  candles: Kline[];
  liveTick?: Kline | null;
  lastClose: string | null;
  onRefresh: () => void;
}) {
  const [showOB, setShowOB] = useState(false);
  const [showFVG, setShowFVG] = useState(false);
  const [planSource, setPlanSource] = useState<PlanSource | null>(null);
  const [plan, setPlan] = useState<ChartPlan | null>(null);
  const [planNote, setPlanNote] = useState<string | null>(null);
  const [planMenu, setPlanMenu] = useState(false);
  const [scenarioOn, setScenarioOn] = useState(false);
  const [scenario, setScenario] = useState<ChartScenario | null>(null);
  const [scenarioNote, setScenarioNote] = useState<string | null>(null);
  const [liqOpen, setLiqOpen] = useState(false);
  const [highlight, setHighlight] = useState<number | null>(null);

  // Reset overlays when the symbol changes — a stale plan/scenario from another
  // symbol must never linger on the chart.
  useEffect(() => {
    setPlanSource(null);
    setPlan(null);
    setPlanNote(null);
    setScenarioOn(false);
    setScenario(null);
    setScenarioNote(null);
    setHighlight(null);
  }, [symbol]);

  // Load the chosen plan source.
  useEffect(() => {
    if (!planSource) {
      setPlan(null);
      setPlanNote(null);
      return;
    }
    let stale = false;
    setPlanNote("loading…");
    const load = async () => {
      try {
        if (planSource === "quickread") {
          const r = await fetchQuickRead(symbol);
          const read = r.read;
          if (!read || read.direction === "no_trade" || !read.entry_zone) {
            if (!stale) { setPlan(null); setPlanNote("Quick Read: no trade"); }
            return;
          }
          if (!stale) {
            setPlan({
              direction: read.direction,
              entryLow: parseFloat(read.entry_zone.low),
              entryHigh: parseFloat(read.entry_zone.high),
              stop: read.stop_loss ? parseFloat(read.stop_loss) : null,
              targets: read.targets.map((t) => ({ price: parseFloat(t.price), rr: t.rr })),
              source: "Quick Read",
            });
            setPlanNote(null);
          }
        } else {
          const r = await fetchPlan(symbol);
          const p = r.plan;
          if (!p || p.direction === "no_trade" || !p.entry_zone) {
            if (!stale) { setPlan(null); setPlanNote(p ? "CIO: stand aside" : r.reason ?? "CIO plan unavailable"); }
            return;
          }
          if (!stale) {
            setPlan({
              direction: p.direction,
              entryLow: parseFloat(p.entry_zone.low),
              entryHigh: parseFloat(p.entry_zone.high),
              stop: p.stop_loss ? parseFloat(p.stop_loss) : null,
              targets: p.targets.map((t) => ({ price: parseFloat(t.price), rr: t.rr })),
              source: "CIO plan",
            });
            setPlanNote(null);
          }
        }
      } catch (e) {
        if (!stale) { setPlan(null); setPlanNote(e instanceof Error ? e.message : "failed"); }
      }
    };
    load();
    return () => {
      stale = true;
    };
  }, [planSource, symbol]);

  // Load the AI scenario when toggled on.
  useEffect(() => {
    if (!scenarioOn) {
      setScenario(null);
      setScenarioNote(null);
      return;
    }
    let stale = false;
    setScenarioNote("mapping…");
    fetchScenario(symbol)
      .then((r) => {
        if (stale) return;
        if (r.status !== "ok" || !r.path) {
          setScenario(null);
          setScenarioNote(r.reason ?? "scenario unavailable");
          return;
        }
        const points = r.path.waypoints
          .filter((w) => w.price != null && w.bar_offset != null)
          .map((w) => ({ price: parseFloat(w.price as string), barOffset: w.bar_offset as number, label: w.label }));
        setScenario({ direction: r.path.direction, points });
        setScenarioNote(r.path.narrative);
      })
      .catch((e) => {
        if (!stale) { setScenario(null); setScenarioNote(e instanceof Error ? e.message : "failed"); }
      });
    return () => {
      stale = true;
    };
  }, [scenarioOn, symbol]);

  const pickLevel = useCallback((price: number) => {
    setHighlight(price);
    setLiqOpen(false);
    window.setTimeout(() => setHighlight((h) => (h === price ? null : h)), 6000);
  }, []);

  const price = lastClose ? parseFloat(lastClose) : null;
  const intact = useMemo(() => levels.filter((l) => l.state !== "broken"), [levels]);

  return (
    <section className="card hud-corners glow-live dp-rise flex h-[380px] min-w-0 flex-col overflow-hidden lg:h-[clamp(360px,50vh,560px)]">
      <div className="flex items-center justify-between border-b border-hair/70 px-5 py-3">
        <div className="flex items-center gap-3">
          <span className="micro-label flex items-center gap-1.5">
            price · {tf}
            <SourceBadge surface="chart" />
          </span>
          {tfa?.structure.last_event && (
            <span className="chip">
              <Term k={tfa.structure.last_event.kind === "BOS" ? "BOS" : "CHOCH"} below>
                <span className={tfa.structure.last_event.direction === "bullish" ? "text-bull" : "text-bear"}>
                  {tfa.structure.last_event.kind}
                </span>
              </Term>{" "}
              @ {formatPrice(tfa.structure.last_event.level)}
            </span>
          )}
        </div>
        <SegTabs value={tf} onChange={setTf} />
      </div>

      <SignalReadout tfa={tfa} levels={levels} price={price} />

      {/* Toolbar */}
      <div className="relative flex flex-wrap items-center gap-1.5 border-b border-hair/60 px-5 py-1.5">
        {/* Plan picker */}
        <div className="relative">
          <ToolButton on={!!plan || planMenu} onClick={() => setPlanMenu((v) => !v)} title="draw a plan on the chart">
            {plan ? `▣ ${plan.source}` : "▣ plan"} ▾
          </ToolButton>
          {planMenu && (
            <div className="absolute top-full left-0 z-20 mt-1 w-40 rounded-md border border-hair bg-panel py-1 shadow-lg">
              {(["quickread", "cio"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => { setPlanSource(s); setPlanMenu(false); }}
                  className={`block w-full px-3 py-1.5 text-left font-mono text-[11px] transition-colors hover:bg-raised ${
                    planSource === s ? "text-hi" : "text-mid"
                  }`}
                >
                  {s === "quickread" ? "Quick Read" : "CIO plan"}
                </button>
              ))}
              <button
                onClick={() => { setPlanSource(null); setPlanMenu(false); }}
                className="block w-full border-t border-hair/50 px-3 py-1.5 text-left font-mono text-[11px] text-dim transition-colors hover:bg-raised hover:text-bear"
              >
                clear
              </button>
            </div>
          )}
        </div>

        <ToolButton on={showOB} onClick={() => setShowOB((v) => !v)} title="order blocks on the chart">
          OB
        </ToolButton>
        <ToolButton on={showFVG} onClick={() => setShowFVG((v) => !v)} title="fair value gaps on the chart">
          FVG
        </ToolButton>
        <ToolButton on={scenarioOn} gold onClick={() => setScenarioOn((v) => !v)} title="AI scenario path — sequence opinion, not a forecast">
          ✦ scenario
        </ToolButton>

        {/* Liquidity jump */}
        <div className="relative">
          <ToolButton on={liqOpen || highlight != null} onClick={() => setLiqOpen((v) => !v)} title="waiting liquidity — click to mark on the chart">
            ◆ liq
          </ToolButton>
          {liqOpen && (
            <div className="absolute top-full left-0 z-20 mt-1 max-h-52 w-56 overflow-y-auto rounded-md border border-hair bg-panel py-1 shadow-lg">
              {intact.length === 0 && (
                <div className="px-3 py-2 font-mono text-[10px] text-dim">no untouched levels</div>
              )}
              {intact.map((l, i) => {
                const lp = parseFloat(l.price);
                const dp = price ? ((lp - price) / price) * 100 : 0;
                return (
                  <button
                    key={`${l.kind}-${i}`}
                    onClick={() => pickLevel(lp)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left font-mono text-[11px] transition-colors hover:bg-raised"
                  >
                    <span className={`w-9 shrink-0 ${l.kind.startsWith("EQ") ? "text-pulse" : "text-warn"}`}>{l.kind}</span>
                    <span className="text-hi">{formatPrice(l.price)}</span>
                    <span className="ml-auto text-dim">{price ? `${dp >= 0 ? "↑" : "↓"}${Math.abs(dp).toFixed(2)}%` : ""}</span>
                    {l.state === "swept" && <span className="text-dim">·swept</span>}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <button
          onClick={onRefresh}
          title="refresh klines + brief"
          className="rounded-md border border-hair px-2 py-[3px] font-mono text-[11px] text-dim transition-colors duration-150 hover:text-hi"
        >
          ↻
        </button>

        {/* Status line for the active overlays */}
        <span className="ml-auto flex items-center gap-2 font-mono text-[9.5px] text-dim">
          {planNote && <span className={planNote.includes("no trade") || planNote.includes("aside") ? "text-warn" : ""}>{planNote}</span>}
          {scenarioOn && (
            <span className="text-gold/70">✦ sequence opinion, not a forecast · দৃশ্যকল্প</span>
          )}
        </span>
      </div>

      <div className="relative min-h-0 flex-1">
        <PriceChart
          candles={candles}
          levels={levels}
          lastEvent={tfa?.structure.last_event ?? null}
          liveTick={liveTick}
          plan={plan}
          orderBlocks={tfa?.order_blocks ?? []}
          fvgs={tfa?.fvgs ?? []}
          showOB={showOB}
          showFVG={showFVG}
          scenario={scenario}
          highlightPrice={highlight}
        />
      </div>
    </section>
  );
}
