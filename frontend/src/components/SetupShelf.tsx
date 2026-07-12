"use client";

/** Trade Setups shelf — one card per venue/style (FR-4 variant fan ·
 *  ADR-0019 + ADR-0022). LIVE: levels come from `/setups/{symbol}`,
 *  computed by the backend engine from the brief (no AI, golden-tested).
 *
 *  ADR-0022 (structure-aware): each directional card first hunts a REAL
 *  unmitigated order block / FVG on its own timeframe and anchors the entry
 *  there; the card shows whether it's "structure-anchored" or an honest
 *  "ATR rule" fallback, a quality grade (high/medium/low), and the exact
 *  confluence reasons that fired. Untradeable variants say WHY (mixed
 *  alignment, no range, missing ATR) instead of showing fake numbers.
 *
 *  The learning loop (ADR-0019): every tradeable directional card has
 *  "＋ journal" — the saved trade auto-grades against real candles on the
 *  journal page, failures ask for a post-mortem, and each variant's real
 *  win record comes back here as a chip once it has ≥1 graded trades.
 *
 *  Live preview + paper desk (owner request, 2026-07-11): while an order is
 *  still pending (price hasn't reached the entry zone) each card shows the
 *  live distance to entry; once price has reached the zone it shows the
 *  hypothetical live R "if filled" — a resting limit order's honest state,
 *  never a fabricated fill. "◇ paper desk" sends the SAME order as a real
 *  PENDING proposal (ADR-0021) — nothing fills until the owner approves it
 *  on the journal page, with real qty/margin/live PnL from that point on.
 *  This is a SECOND action beside "＋ journal", not a replacement — the
 *  journal button still feeds the win-rate chips and the CIO lessons loop.
 *
 *  Venue labels are chrome (neutral); direction + quality are semantic
 *  teal/amber/red; live/pending state is pulse-cyan (live data, never
 *  chrome/gold — C6a); the strategy name stays the card's single gold
 *  accent (ADR-0010). Structure/quality are ENGINE facts — never gold.
 */

import { useCallback, useEffect, useState } from "react";

import SourceBadge from "@/components/SourceBadge";
import Term from "@/components/Term";
import {
  fetchLessons,
  fetchSetups,
  formatPrice,
  proposeOrder,
  type LessonsDigest,
  type SetupVariant,
  type SetupsResponse,
} from "@/lib/api";
import type { GlossaryKey } from "@/lib/glossary";
import { addTrade } from "@/lib/journal";
import { dirKey } from "@/lib/terms";

type ProposeState = "idle" | "busy" | "done" | "error";

/** A resting limit order's honest live state: still waiting for price to
 *  reach the entry zone, or reached it (would be filled at the same "worse
 *  edge" the backtest/paper-broker fill at — ADR-0020/0021), in which case
 *  the hypothetical R is shown. Never claims a fill that hasn't happened. */
function liveStatus(
  v: SetupVariant,
  livePrice: string | null,
): { state: "waiting"; distPct: number } | { state: "filled"; r: number } | null {
  if (!v.tradeable || v.direction === "neutral" || !v.entry_low || !v.entry_high || !v.stop || !livePrice) {
    return null;
  }
  const price = Number(livePrice);
  const entryRef = Number(v.direction === "long" ? v.entry_high : v.entry_low);
  const stop = Number(v.stop);
  if (!isFinite(price) || !isFinite(entryRef) || !isFinite(stop)) return null;
  const risk = Math.abs(entryRef - stop);
  if (risk <= 0) return null;

  const reached = v.direction === "long" ? price <= entryRef : price >= entryRef;
  if (!reached) {
    const distPct = Math.abs((price - entryRef) / entryRef) * 100;
    return { state: "waiting", distPct };
  }
  const moved = v.direction === "long" ? price - entryRef : entryRef - price;
  return { state: "filled", r: moved / risk };
}

const POLL_MS = 60_000; // levels ride the brief's cache; this keeps them fresh

const META: Record<
  SetupVariant["key"],
  { venue: string; venueTerm: GlossaryKey; name: string; bn: string; risk: 1 | 2 | 3 | 4 | 5 }
> = {
  scalp: { venue: "PERP · USDⓈ-M", venueTerm: "PERP", name: "Liquidity scalp", bn: "দ্রুত ছোট লাভ", risk: 4 },
  intraday: { venue: "PERP · USDⓈ-M", venueTerm: "PERP", name: "Intraday continuation", bn: "দিনের ট্রেন্ড ধরে", risk: 3 },
  swing: { venue: "MARGIN", venueTerm: "MARGIN", name: "Structure swing", bn: "কাঠামো ধরে সুইং", risk: 2 },
  spot: { venue: "SPOT", venueTerm: "SPOT", name: "Swing accumulate", bn: "ধীরে ধীরে জমানো", risk: 1 },
  grid: { venue: "GRID BOT", venueTerm: "GRID", name: "Range harvest", bn: "রেঞ্জ থেকে আয়", risk: 2 },
  options: { venue: "OPTIONS", venueTerm: "OPTIONS", name: "Covered call", bn: "হোল্ডিং থেকে আয়", risk: 2 },
};

const dirStyle: Record<SetupVariant["direction"], { label: string; cls: string }> = {
  long: { label: "▲ long", cls: "text-bull border-bull/40" },
  short: { label: "▼ short", cls: "text-bear border-bear/40" },
  neutral: { label: "◆ neutral", cls: "text-mid border-hair" },
};

// Quality tier (ADR-0022) — an engine grade, never gold. high = teal,
// medium = amber, low = muted. Bilingual label for the chip.
const qualityStyle: Record<"high" | "medium" | "low", { cls: string; bn: string }> = {
  high: { cls: "text-bull border-bull/40", bn: "উচ্চ" },
  medium: { cls: "text-warn border-warn/40", bn: "মাঝারি" },
  low: { cls: "text-dim border-hair", bn: "নিম্ন" },
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

function rows(v: SetupVariant): Array<[string, string]> {
  if (!v.tradeable || !v.entry_low) return [];
  if (v.key === "grid") return [["range", `${formatPrice(v.entry_low)} – ${formatPrice(v.entry_high!)}`]];
  if (v.key === "options") return [["strike", formatPrice(v.entry_low)]];
  const out: Array<[string, string]> = [
    ["entry", v.entry_high && v.entry_high !== v.entry_low ? `${formatPrice(v.entry_low)} – ${formatPrice(v.entry_high)}` : formatPrice(v.entry_low)],
  ];
  if (v.stop) out.push(["stop", formatPrice(v.stop)]);
  v.targets.forEach((t, i) => out.push([`tp${i + 1} · r:r`, `${formatPrice(t.price)} · ${t.rr.toFixed(2)}R`]));
  return out;
}

export default function SetupShelf({
  symbol,
  livePrice = null,
}: {
  symbol: string;
  livePrice?: string | null;
}) {
  const [data, setData] = useState<SetupsResponse | null>(null);
  const [lessons, setLessons] = useState<LessonsDigest | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [proposed, setProposed] = useState<Record<string, ProposeState>>({});

  const load = useCallback(() => {
    fetchSetups(symbol).then(setData).catch(() => setData(null));
    fetchLessons().then(setLessons).catch(() => {});
  }, [symbol]);

  useEffect(() => {
    setData(null);
    setSaved(new Set());
    setProposed({});
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const save = (v: SetupVariant) => {
    if (!v.tradeable || !v.gradeable || !v.entry_low || !v.stop || saved.has(v.key)) return;
    if (v.direction === "neutral") return;
    addTrade({
      symbol,
      dir: v.direction,
      conviction: 3, // engine scaffold — neutral conviction, not an AI's opinion
      entryLow: v.entry_low,
      entryHigh: v.entry_high,
      stop: v.stop,
      target: v.targets[0]?.price ?? null,
      targetRR: v.targets[0]?.rr ?? null,
      thesis: `${META[v.key].name} (${v.style}, ${v.anchor_tf}, ${
        v.entry_kind === "structure" ? `${v.quality} structure` : "ATR fallback"
      }) — ${v.edge}`,
      source: "setup",
      variant: v.key,
    });
    setSaved((prev) => new Set(prev).add(v.key));
  };

  // Sends the SAME order to the paper desk as a PENDING proposal (ADR-0021).
  // Nothing fills here — approving it (journal page) is a separate, human,
  // explicit step; that's where real qty/margin/live PnL start ticking.
  const proposeToPaperDesk = async (v: SetupVariant) => {
    if (!v.tradeable || !v.gradeable || !v.entry_low || !v.entry_high || !v.stop) return;
    if (v.direction === "neutral") return;
    if ((proposed[v.key] ?? "idle") !== "idle") return;
    setProposed((p) => ({ ...p, [v.key]: "busy" }));
    try {
      await proposeOrder({
        symbol,
        direction: v.direction,
        entry_low: v.entry_low,
        entry_high: v.entry_high,
        stop: v.stop,
        targets: v.targets.map((t) => t.price),
        thesis: `${META[v.key].name} (${v.style}, ${v.anchor_tf}, ${
          v.entry_kind === "structure" ? `${v.quality} structure` : "ATR fallback"
        }) — ${v.edge}`.slice(0, 600),
      });
      setProposed((p) => ({ ...p, [v.key]: "done" }));
    } catch {
      setProposed((p) => ({ ...p, [v.key]: "error" }));
    }
  };

  const variants = data?.variants ?? [];

  return (
    <section
      className="card dp-rise flex flex-col overflow-hidden lg:min-h-0 lg:flex-1"
      style={{ animationDelay: "80ms" }}
    >
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-hair/70 px-5 py-2.5">
        <span className="min-w-0">
          <span className="flex items-center gap-1.5">
            <span className="micro-label block">
              trade setups · {symbol} · engine variants
            </span>
            <SourceBadge surface="setups" />
          </span>
          <span className="bn-sub mt-0.5">ট্রেড সেটআপ — কোন মার্কেটে কীভাবে</span>
        </span>
        {data && (
          <span className="shrink-0 rounded-md border border-hair px-2 py-px font-mono text-[9px] tracking-[0.12em] text-bull">
            LIVE · bias {data.bias}
          </span>
        )}
      </div>
      {/* Vertical stack — one bordered tile per venue, serially down with gaps;
          scrolls inside its box so it fills the column without breaking one-screen. */}
      <div className="flex flex-col gap-3 p-3 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
        {variants.length === 0 && (
          <div className="px-2 py-6 text-center text-[12px] text-dim">
            computing variants… <span className="font-bn">সেটআপ হিসাব হচ্ছে…</span>
          </div>
        )}
        {variants.map((v, i) => {
          const m = META[v.key];
          const d = dirStyle[v.direction];
          const stats = lessons?.by_variant[`setup:${v.key}`];
          const isSaved = saved.has(v.key);
          return (
            <article
              key={v.key}
              className={`setup-tile dp-rise rounded-[10px] border border-hair bg-abyss/40 px-4 py-3 ${
                v.tradeable ? "" : "opacity-70"
              }`}
              style={{ animationDelay: `${120 + i * 45}ms` }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[9.5px] tracking-[0.14em] text-dim">
                      <Term k={m.venueTerm}>{m.venue}</Term>
                      {v.leverage > 1 && <span className="text-warn"> · {v.leverage}×</span>}
                    </span>
                    <span className={`rounded-md border px-1.5 py-px font-mono text-[9.5px] ${d.cls}`}>
                      <Term k={dirKey(v.direction)} bare>{d.label}</Term>
                    </span>
                    <span className="font-mono text-[9.5px] text-dim">· {v.anchor_tf}</span>
                    {v.quality && (
                      <span
                        className={`rounded-md border px-1.5 py-px font-mono text-[9px] uppercase tracking-[0.08em] ${qualityStyle[v.quality].cls}`}
                        title="engine confluence grade (ADR-0022) — not an AI opinion"
                      >
                        {v.quality} <span className="font-bn">· {qualityStyle[v.quality].bn}</span>
                      </span>
                    )}
                    {stats && stats.n > 0 && (
                      <span
                        className={`rounded-md border border-hair px-1.5 py-px font-mono text-[9px] tabular-nums ${
                          stats.win_rate == null ? "text-dim" : stats.win_rate >= 0.5 ? "text-bull" : "text-bear"
                        }`}
                        title="this variant's graded record (your journal)"
                      >
                        {stats.wins}W {stats.losses}L
                        {stats.win_rate != null ? ` · ${Math.round(stats.win_rate * 100)}%` : ""}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-[15px] font-semibold leading-tight text-gold/95">{m.name}</div>
                  <div className="bn-sub mt-0.5">{m.bn}</div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <RiskDots level={m.risk} />
                  <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-dim">risk {m.risk}/5</span>
                </div>
              </div>

              {v.tradeable ? (
                <div className="mt-2 space-y-1">
                  {rows(v).map(([k, val]) => (
                    <div key={k} className="flex items-center text-[11.5px]">
                      <span className="w-[70px] shrink-0 font-mono text-[9.5px] font-medium uppercase tracking-[0.08em] text-mid">
                        {k}
                      </span>
                      <span className="leader" />
                      <span className="font-mono tabular-nums text-hi">{val}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 rounded-md border border-hair/60 bg-abyss/40 px-2.5 py-1.5 text-[10.5px] leading-snug text-warn/80">
                  ◆ {v.reason ?? "no valid setup right now"}
                </p>
              )}

              {/* Live preview — a resting limit order's honest state. Never a
                  fabricated fill: "waiting" until price actually reaches the
                  entry zone, only then does the hypothetical R appear. */}
              {(() => {
                const status = liveStatus(v, livePrice);
                if (!status) return null;
                if (status.state === "waiting") {
                  return (
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <span className="live-dot bg-raised" />
                      <span className="font-mono text-[10px] tabular-nums text-dim">
                        {status.distPct.toFixed(2)}% from entry
                      </span>
                      <span className="bn-sub">এন্ট্রি থেকে দূরত্ব</span>
                    </div>
                  );
                }
                const tone = status.r > 0 ? "text-bull" : status.r < 0 ? "text-bear" : "text-mid";
                return (
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <span className="live-dot bg-pulse" />
                    <span className={`font-mono text-[10.5px] tabular-nums ${tone}`}>
                      live if filled: {status.r > 0 ? "+" : ""}
                      {status.r.toFixed(2)}R
                    </span>
                    <span className="bn-sub">এখন পূরণ হলে</span>
                  </div>
                );
              })()}

              {/* ADR-0022: how this entry was chosen + the reasons that fired.
                  Structure-anchored = real zone (teal); fallback = honest ATR
                  rule (muted). Reasons are computed facts, never AI. */}
              {v.tradeable && v.quality && (
                <div className="mt-2 rounded-md border border-hair/50 bg-abyss/30 px-2.5 py-1.5">
                  <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                    {v.entry_kind === "structure" ? (
                      <>
                        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-bull">
                          ◆ structure-anchored
                        </span>
                        <span className="bn-sub">আসল কাঠামোয় বসানো এন্ট্রি</span>
                      </>
                    ) : (
                      <>
                        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-dim">
                          ATR rule · no zone in range
                        </span>
                        <span className="bn-sub">কাছে জোন নেই — ATR নিয়মে</span>
                      </>
                    )}
                  </div>
                  {v.confluence.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {v.confluence.map((c, idx) => (
                        <li key={idx} className="flex items-start gap-1 text-[10px] leading-snug text-mid">
                          <span className="mt-px shrink-0 text-bull">✓</span>
                          <span>{c}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <p className="mt-2 text-[11px] leading-snug text-mid">{v.edge}</p>
              <p className="font-bn mt-0.5 text-[11px] leading-snug text-dim">{v.edge_bn}</p>

              {v.tradeable && v.gradeable && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => save(v)}
                    disabled={isSaved}
                    className={`rounded-md border px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] transition-colors duration-150 ${
                      isSaved
                        ? "border-bull/40 text-bull"
                        : "border-hair text-mid hover:border-pulse/40 hover:text-hi"
                    }`}
                    title="saves to the journal for grading + the CIO lessons loop (ADR-0019)"
                  >
                    {isSaved ? "✓ saved · journal" : "＋ journal · জার্নালে যোগ"}
                  </button>
                  <button
                    onClick={() => void proposeToPaperDesk(v)}
                    disabled={(proposed[v.key] ?? "idle") !== "idle"}
                    className={`rounded-md border px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] transition-colors duration-150 ${
                      (proposed[v.key] ?? "idle") === "done"
                        ? "border-pulse/50 text-pulse"
                        : (proposed[v.key] ?? "idle") === "error"
                          ? "border-bear/40 text-bear"
                          : "border-hair text-mid hover:border-pulse/40 hover:text-hi"
                    }`}
                    title="sends a PENDING order to the paper desk — nothing fills until you approve it there (ADR-0021)"
                  >
                    {(proposed[v.key] ?? "idle") === "done"
                      ? "✓ proposed · approve in journal"
                      : (proposed[v.key] ?? "idle") === "error"
                        ? "✕ retry"
                        : "◇ paper desk · কাগুজে ডেস্ক"}
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
