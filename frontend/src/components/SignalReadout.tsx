"use client";

/** Signal Readout — a compact strip of deterministic reads pulled straight
 *  from the Market Brief (structure, RSI, EMA stack, VWAP side, ATR%, nearest
 *  liquidity). No AI, no guessing: every chip is a fact the engine computed,
 *  each abbreviation hover-explained in Bengali. This is the "important signal
 *  text" that makes the chart read like a desk, not just candles.
 */

import Term from "@/components/Term";
import { formatPrice, type LevelOut, type TimeframeAnalysis } from "@/lib/api";
import type { GlossaryKey } from "@/lib/glossary";
import { trendKey } from "@/lib/terms";

type Tone = "bull" | "bear" | "warn" | "mid" | "dim";
const toneCls: Record<Tone, string> = {
  bull: "text-bull",
  bear: "text-bear",
  warn: "text-warn",
  mid: "text-mid",
  dim: "text-dim",
};

function pctOf(a: number, b: number): number {
  return b ? ((a - b) / b) * 100 : 0;
}

function Chip({
  term,
  label,
  value,
  tone,
}: {
  term: GlossaryKey;
  label: string;
  value: string;
  tone: Tone;
}) {
  return (
    <span className="flex shrink-0 items-baseline gap-1.5 rounded-md border border-hair/70 bg-abyss/40 px-2 py-[3px]">
      <Term k={term} className="font-mono text-[9px] uppercase tracking-[0.1em] text-mid">
        {label}
      </Term>
      <span className={`font-mono text-[10.5px] tabular-nums ${toneCls[tone]}`}>{value}</span>
    </span>
  );
}

export default function SignalReadout({
  tfa,
  levels,
  price,
}: {
  tfa?: TimeframeAnalysis;
  levels: LevelOut[];
  price: number | null;
}) {
  if (!tfa || price == null) {
    return (
      <div className="flex shrink-0 items-center gap-2 border-b border-hair/60 px-5 py-2">
        <span className="flex items-baseline gap-2">
          <Term k="SIGNAL" className="micro-label">signals</Term>
          <span className="bn-sub">সংকেত</span>
        </span>
        <span className="ml-auto font-mono text-[10px] text-dim">calibrating…</span>
      </div>
    );
  }

  const ind = tfa.indicators;
  const chips: React.ReactNode[] = [];

  // Structure / trend
  const trend = tfa.structure.trend;
  chips.push(
    <Chip
      key="trend"
      term={trendKey(trend)}
      label="trend"
      value={trend}
      tone={trend === "bullish" ? "bull" : trend === "bearish" ? "bear" : "mid"}
    />,
  );

  // RSI momentum
  const rsi = ind.rsi14;
  if (rsi != null) {
    const state = rsi >= 70 ? "ওভারবট" : rsi <= 30 ? "ওভারসোল্ড" : "মাঝামাঝি";
    chips.push(
      <Chip
        key="rsi"
        term="RSI"
        label="rsi"
        value={`${rsi.toFixed(0)} · ${state}`}
        tone={rsi >= 70 ? "bear" : rsi <= 30 ? "bull" : "mid"}
      />,
    );
  }

  // EMA stack
  const { ema20, ema50, ema200 } = ind;
  if (ema20 != null && ema50 != null) {
    const bull = ema200 != null ? ema20 > ema50 && ema50 > ema200 : ema20 > ema50;
    const bear = ema200 != null ? ema20 < ema50 && ema50 < ema200 : ema20 < ema50;
    chips.push(
      <Chip
        key="ema"
        term="EMA"
        label="ema"
        value={bull ? "সাজানো ↑" : bear ? "সাজানো ↓" : "মিশ্র"}
        tone={bull ? "bull" : bear ? "bear" : "mid"}
      />,
    );
  }

  // VWAP side
  const vwap = ind.vwap;
  if (vwap != null) {
    const above = price >= vwap;
    chips.push(
      <Chip key="vwap" term="VWAP" label="vwap" value={above ? "উপরে" : "নিচে"} tone={above ? "bull" : "bear"} />,
    );
  }

  // ATR as % of price (volatility)
  const atr = ind.atr14;
  if (atr != null) {
    chips.push(<Chip key="atr" term="ATR" label="atr" value={`${pctOf(price + atr, price).toFixed(2)}%`} tone="mid" />);
  }

  // Nearest liquidity level
  if (levels.length) {
    let near: LevelOut = levels[0];
    let best = Infinity;
    for (const lv of levels) {
      const d = Math.abs(price - parseFloat(lv.price));
      if (d < best) {
        best = d;
        near = lv;
      }
    }
    const dp = pctOf(parseFloat(near.price), price);
    chips.push(
      <Chip
        key="liq"
        term="LIQUIDITY"
        label={near.kind}
        value={`${formatPrice(near.price)} · ${dp >= 0 ? "+" : ""}${dp.toFixed(2)}%`}
        tone="warn"
      />,
    );
  }

  return (
    <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-hair/60 px-5 py-2">
      <span className="flex shrink-0 items-baseline gap-2">
        <Term k="SIGNAL" className="micro-label">signals</Term>
        <span className="bn-sub">সংকেত</span>
      </span>
      <span className="mx-1 h-3.5 w-px shrink-0 bg-hair" />
      <span className="flex items-center gap-2">{chips}</span>
    </div>
  );
}
