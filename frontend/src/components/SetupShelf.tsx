"use client";

/** Trade Setups shelf — one card per Binance venue/style (FR-4 setup
 *  variants): spot accumulate, USDⓈ-M perp intraday + scalp, margin swing,
 *  options income, grid bot. Horizontally scrollable blotter under the
 *  chart. Venue labels are chrome (neutral); direction is semantic
 *  teal/red; the strategy name is the card's single gold accent — these
 *  are AI-proposed setups (ADR-0010: judgment is gold).
 *
 *  DEMO DATA: numbers are placeholders scaled off the live price so
 *  proportions read true. P2 replaces this with real TradePlan variants.
 */

import SampleTag from "@/components/SampleTag";
import Term from "@/components/Term";
import type { GlossaryKey } from "@/lib/glossary";
import { dirKey } from "@/lib/terms";

type Setup = {
  venue: string;
  venueTerm: GlossaryKey;
  lev: string | null;
  name: string;
  bn: string;
  dir: "long" | "short" | "neutral";
  tf: string;
  risk: 1 | 2 | 3 | 4 | 5;
  rows: (p: number) => Array<[string, string]>;
  edge: string;
  edgeBn: string;
};

function f(n: number): string {
  const digits = n >= 1000 ? 0 : n >= 1 ? 2 : 6;
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

const SETUPS: Setup[] = [
  {
    venue: "SPOT",
    venueTerm: "SPOT",
    lev: null,
    name: "Swing accumulate",
    bn: "ধীরে ধীরে জমানো",
    dir: "long",
    tf: "4h–1d",
    risk: 1,
    rows: (p) => [
      ["entry", `${f(p * 0.97)} – ${f(p * 0.985)}`],
      ["target", f(p * 1.08)],
      ["invalid", `< ${f(p * 0.942)}`],
    ],
    edge: "DCA into 4H demand — no liquidation risk, time works for you.",
    edgeBn: "৪ঘণ্টার ডিমান্ডে ধীরে ধীরে কিনুন — লিকুইডেশনের ভয় নেই, সময় আপনার পক্ষে।",
  },
  {
    venue: "PERP · USDⓈ-M",
    venueTerm: "PERP",
    lev: "3×",
    name: "Intraday continuation",
    bn: "দিনের ট্রেন্ড ধরে",
    dir: "long",
    tf: "1h",
    risk: 3,
    rows: (p) => [
      ["entry", `${f(p * 0.9945)} – ${f(p * 0.9985)}`],
      ["stop", f(p * 0.9865)],
      ["tp2 · r:r", `${f(p * 1.024)} · 2.9R`],
    ],
    edge: "Funding neutral — leverage without paying a crowding tax.",
    edgeBn: "ফান্ডিং নিউট্রাল — ভিড়ের বাড়তি খরচ ছাড়াই লিভারেজ নেওয়া যায়।",
  },
  {
    venue: "PERP · USDⓈ-M",
    venueTerm: "PERP",
    lev: "5×",
    name: "Liquidity scalp",
    bn: "দ্রুত ছোট লাভ",
    dir: "long",
    tf: "15m",
    risk: 4,
    rows: (p) => [
      ["entry", f(p * 0.9982)],
      ["stop", f(p * 0.9952)],
      ["tp · r:r", `${f(p * 1.0037)} · 1.8R`],
    ],
    edge: "Sweep-and-reclaim at the equal lows; in fast, out faster.",
    edgeBn: "সমান লো-তে সুইপ করে ফিরে আসা; দ্রুত ঢোকা, আরও দ্রুত বেরোনো।",
  },
  {
    venue: "MARGIN",
    venueTerm: "MARGIN",
    lev: "2×",
    name: "Structure swing",
    bn: "কাঠামো ধরে সুইং",
    dir: "long",
    tf: "4h",
    risk: 2,
    rows: (p) => [
      ["entry", `${f(p * 0.978)} – ${f(p * 0.99)}`],
      ["stop", f(p * 0.958)],
      ["tp · r:r", `${f(p * 1.065)} · 3.2R`],
    ],
    edge: "BOS-confirmed trend with room to premium — modest leverage.",
    edgeBn: "কাঠামো-নিশ্চিত ট্রেন্ড, প্রিমিয়াম পর্যন্ত জায়গা আছে — অল্প লিভারেজ।",
  },
  {
    venue: "OPTIONS",
    venueTerm: "OPTIONS",
    lev: null,
    name: "Covered call",
    bn: "হোল্ডিং থেকে আয়",
    dir: "neutral",
    tf: "7d expiry",
    risk: 2,
    rows: (p) => [
      ["strike", f(p * 1.05)],
      ["premium", "≈ 1.2% / wk"],
      ["assigned if", `> ${f(p * 1.05)}`],
    ],
    edge: "Yield on spot holdings while structure grinds, not trends.",
    edgeBn: "বাজার ট্রেন্ড না করে ঘোরাঘুরি করলে হাতের কয়েন থেকে আয়।",
  },
  {
    venue: "GRID BOT",
    venueTerm: "GRID",
    lev: null,
    name: "Range harvest",
    bn: "রেঞ্জ থেকে আয়",
    dir: "neutral",
    tf: "auto",
    risk: 2,
    rows: (p) => [
      ["range", `${f(p * 0.94)} – ${f(p * 1.04)}`],
      ["grids", "24 · geometric"],
      ["est. yield", "≈ 0.18% / day"],
    ],
    edge: "Monetizes chop between liquidity shelves; kill on breakout.",
    edgeBn: "দুই লিকুইডিটি স্তরের মাঝের ওঠানামা থেকে আয়; ব্রেকআউট হলে বন্ধ।",
  },
];

const dirStyle: Record<Setup["dir"], { label: string; cls: string }> = {
  long: { label: "▲ long", cls: "text-bull border-bull/40" },
  short: { label: "▼ short", cls: "text-bear border-bear/40" },
  neutral: { label: "◆ neutral", cls: "text-mid border-hair" },
};

function RiskDots({ level }: { level: number }) {
  const color = level >= 4 ? "var(--bear)" : level >= 3 ? "var(--warn)" : "var(--bull)";
  return (
    <span className="inline-flex items-center gap-[3px]" title={`risk ${level}/5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className="h-[5px] w-[5px] rounded-full"
          style={{ background: i < level ? color : "var(--bg-raised)" }}
        />
      ))}
    </span>
  );
}

export default function SetupShelf({ symbol, price }: { symbol: string; price: number | null }) {
  const p = price ?? 100_000;
  return (
    <section
      className="card dp-rise flex flex-col overflow-hidden lg:min-h-0 lg:flex-1"
      style={{ animationDelay: "80ms" }}
    >
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-hair/70 px-5 py-2.5">
        <span className="min-w-0">
          <span className="micro-label block">
            trade setups · {symbol} · {SETUPS.length} venues
          </span>
          <span className="bn-sub mt-0.5">ট্রেড সেটআপ — কোন মার্কেটে কীভাবে</span>
        </span>
        <SampleTag />
      </div>
      {/* Vertical stack — one bordered tile per venue, serially down with gaps;
          scrolls inside its box so it fills the column without breaking one-screen. */}
      <div className="flex flex-col gap-3 p-3 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
        {SETUPS.map((s, i) => {
          const d = dirStyle[s.dir];
          return (
            <article
              key={s.venue + s.name}
              className="setup-tile dp-rise rounded-[10px] border border-hair bg-abyss/40 px-4 py-3"
              style={{ animationDelay: `${120 + i * 45}ms` }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[9.5px] tracking-[0.14em] text-dim">
                      <Term k={s.venueTerm}>{s.venue}</Term>
                      {s.lev && <span className="text-warn"> · {s.lev}</span>}
                    </span>
                    <span className={`rounded-md border px-1.5 py-px font-mono text-[9.5px] ${d.cls}`}>
                      <Term k={dirKey(s.dir)} bare>{d.label}</Term>
                    </span>
                    <span className="font-mono text-[9.5px] text-dim">· {s.tf}</span>
                  </div>
                  <div className="mt-1 text-[15px] font-semibold leading-tight text-gold/95">{s.name}</div>
                  <div className="bn-sub mt-0.5">{s.bn}</div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <RiskDots level={s.risk} />
                  <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-dim">risk {s.risk}/5</span>
                </div>
              </div>
              <div className="mt-2 space-y-1">
                {s.rows(p).map(([k, v]) => (
                  <div key={k} className="flex items-center text-[11.5px]">
                    <span className="w-[70px] shrink-0 font-mono text-[9.5px] font-medium uppercase tracking-[0.08em] text-mid">
                      {k}
                    </span>
                    <span className="leader" />
                    <span className="font-mono tabular-nums text-hi">{v}</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] leading-snug text-mid">{s.edge}</p>
              <p className="font-bn mt-0.5 text-[11px] leading-snug text-dim">{s.edgeBn}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
