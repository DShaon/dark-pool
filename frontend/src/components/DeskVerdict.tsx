"use client";

/** Desk Verdict — the AI layer's one flooded-gold moment (C4 signature #1).
 *  Reveal sequence: seat chips flare in → the conviction arc pours → the
 *  serif verdict word converges from tracked-out letters.
 *
 *  LIVE MODE: renders a real, schema-validated, evidence-locked Quick Read
 *  from /quickread/{symbol} (FR-3 tier 1). Every number came from the
 *  Market Brief — the evidence line says how many citations were verified.
 *  DEMO MODE: placeholder plan scaled off the live price, shown until the
 *  first read lands (or when the backend has no LLM key). Tagged honestly.
 */

import { useEffect, useMemo, useState } from "react";

import SampleTag from "@/components/SampleTag";
import SourceBadge from "@/components/SourceBadge";
import Term from "@/components/Term";
import { formatPrice, type QuickReadResponse } from "@/lib/api";
import type { GlossaryKey } from "@/lib/glossary";
import { addTrade } from "@/lib/journal";
import { dirKey } from "@/lib/terms";

const DEMO_MANDATES = [
  { key: "trend", label: "TREND", agrees: true },
  { key: "contrarian", label: "CNTRN", agrees: false },
  { key: "derivatives", label: "DERIV", agrees: true },
  { key: "risk", label: "RISK", agrees: true },
] as const;

/** Serif verdict word — letters start pushed outward (fake wide tracking),
 *  converge to set. Distance from center drives each letter's travel. */
function VerdictWord({ word, runId, color }: { word: string; runId: string; color: string }) {
  const letters = word.split("");
  const mid = (letters.length - 1) / 2;
  return (
    <span key={runId} className="font-bold tracking-[-0.01em]" style={{ color }} aria-label={word}>
      {letters.map((ch, i) => (
        <span
          key={i}
          className="verdict-letter"
          style={{
            ["--lx" as string]: `${(i - mid) * 0.22}em`,
            animationDelay: `${340 + i * 30}ms`,
          }}
        >
          {ch === " " ? " " : ch}
        </span>
      ))}
    </span>
  );
}

/** Conviction arc — pours like metal to conviction/5. Hue follows the
 *  direction (data semantics); the numeral itself stays gold (judgment). */
function ConvictionArc({
  value,
  label,
  hue,
  runId,
}: {
  value: number; // 0..1
  label: string;
  hue: string;
  runId: string;
}) {
  const [poured, setPoured] = useState(false);
  useEffect(() => {
    setPoured(false);
    const id = requestAnimationFrame(() => requestAnimationFrame(() => setPoured(true)));
    return () => cancelAnimationFrame(id);
  }, [runId]);

  const R = 30;
  const C = 2 * Math.PI * R * 0.75; // 270° arc

  return (
    <div className="relative h-[76px] w-[76px] shrink-0">
      <svg width="76" height="76" viewBox="0 0 76 76" className="-rotate-[135deg]">
        <circle
          cx="38" cy="38" r={R} fill="none"
          stroke="var(--line-hair)" strokeWidth="4"
          strokeDasharray={`${C} ${2 * Math.PI * R}`} strokeLinecap="round"
        />
        <circle
          cx="38" cy="38" r={R} fill="none"
          stroke={hue} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={`${C} ${2 * Math.PI * R}`}
          strokeDashoffset={poured ? C * (1 - value) : C}
          className="arc-pour"
          style={{ transitionDelay: "420ms" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-[15px] font-light tabular-nums text-gold">
          {label}
        </span>
        <Term k="CONVICTION" bare className="text-[9px] uppercase tracking-[0.16em] text-mid">
          conv
        </Term>
      </div>
    </div>
  );
}

function Row({
  label,
  term,
  children,
}: {
  label: string;
  term?: GlossaryKey;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center text-xs">
      <span className="w-16 shrink-0 font-mono text-[10.5px] font-medium uppercase tracking-[0.1em] text-mid">
        {term ? <Term k={term}>{label}</Term> : label}
      </span>
      <span className="leader" />
      <span className="text-right font-mono text-[12.5px] tabular-nums text-hi">{children}</span>
    </div>
  );
}

const DIR_META = {
  long: { word: "LONG", hue: "var(--bull)" },
  short: { word: "SHORT", hue: "var(--bear)" },
  no_trade: { word: "STAND ASIDE", hue: "var(--text-dim)" },
} as const;

export default function DeskVerdict({
  symbol,
  price,
  data,
  running,
  onRun,
}: {
  symbol: string;
  price: number | null;
  data: QuickReadResponse | null;
  running: boolean;
  onRun: () => void;
}) {
  const [replayId, setReplayId] = useState(0);
  const [saved, setSaved] = useState(false);

  const read = data?.status === "ok" ? data.read : null;
  const live = read !== null && read !== undefined;
  const runId = `${data?.generated_at ?? "demo"}-${replayId}`;
  const canSave = live && read.direction !== "no_trade";

  // Reset the "saved" confirmation when the read changes or after a moment.
  useEffect(() => setSaved(false), [runId, symbol]);
  useEffect(() => {
    if (!saved) return;
    const id = setTimeout(() => setSaved(false), 2400);
    return () => clearTimeout(id);
  }, [saved]);

  const saveToJournal = () => {
    if (!canSave) return;
    addTrade({
      symbol,
      dir: read.direction,
      conviction: read.conviction,
      entryLow: read.entry_zone?.low ?? null,
      entryHigh: read.entry_zone?.high ?? null,
      stop: read.stop_loss ?? null,
      target: read.targets[0]?.price ?? null,
      targetRR: read.targets[0]?.rr ?? null,
      thesis: read.thesis,
      source: "quick_read",
    });
    setSaved(true);
  };

  // Demo fallback plan scaled off the live price — display-only placeholder.
  const demo = useMemo(() => {
    const p = price ?? 100_000;
    return {
      entryLow: p * 0.9945,
      entryHigh: p * 0.9985,
      stop: p * 0.9865,
      tps: [
        { px: p * 1.012, rr: 1.6 },
        { px: p * 1.024, rr: 2.9 },
        { px: p * 1.041, rr: 4.4 },
      ],
      invalidation: p * 0.9852,
    };
  }, [price]);

  const dirMeta = live ? DIR_META[read.direction] : DIR_META.long;
  const wordSize = live && read.direction === "no_trade" ? "text-[34px]" : "text-[54px]";

  return (
    <div className="card card-ai glow-ai dp-rise overflow-hidden">
      <div className="flex items-center justify-between border-b border-[rgba(232,197,116,0.18)] px-5 py-3">
        <span className="flex items-baseline gap-2.5">
          <Term k="QUICK_READ" below className="micro-label">
            <span style={{ color: "var(--ai-gold)", opacity: 0.9 }}>desk verdict · quick read</span>
          </Term>
          <SourceBadge surface="quickread" detail={data?.model_id ?? null} />
          <span className="bn-sub">ডেস্কের রায়</span>
        </span>
        <div className="flex items-center gap-2.5">
          {running ? (
            <span className="demo-tag">RUNNING</span>
          ) : live ? (
            <span className="demo-tag" title={data?.model_id}>LIVE</span>
          ) : data?.status === "degraded" ? (
            <span className="demo-tag">DROPPED</span>
          ) : (
            <SampleTag />
          )}
          <button
            onClick={() => (live || data ? onRun() : setReplayId((n) => n + 1))}
            disabled={running}
            className="font-mono text-[11px] text-dim transition-colors duration-200 hover:text-gold disabled:opacity-40"
            title={live || data ? "re-run quick read" : "replay reveal"}
            aria-label="run quick read"
          >
            ⟳
          </button>
        </div>
      </div>

      <div className="px-5 pt-4 pb-5">
        {/* Seat chips — live: single quick-read seat + model; demo: 4 mandates */}
        <div key={`chips-${runId}`} className="flex flex-wrap gap-1.5">
          {live ? (
            <>
              <span
                className="mandate-flare rounded-md border px-2.5 py-1 text-center font-mono text-[9px] tracking-[0.12em]"
                style={{ borderColor: "rgba(232,197,116,0.4)", color: "var(--ai-gold)" }}
              >
                QUICK READ
              </span>
              <span
                className="mandate-flare rounded-md border border-hair px-2.5 py-1 text-center font-mono text-[9px] tracking-[0.12em] text-dim"
                style={{ animationDelay: "80ms" }}
              >
                {data?.model_id}
              </span>
            </>
          ) : (
            DEMO_MANDATES.map((m, i) => (
              <span
                key={m.key}
                className="mandate-flare flex-1 rounded-md border px-0 py-1 text-center font-mono text-[9px] tracking-[0.12em]"
                style={{
                  animationDelay: `${i * 80}ms`,
                  borderColor: m.agrees ? "rgba(232,197,116,0.4)" : "var(--line-hair)",
                  color: m.agrees ? "var(--ai-gold)" : "var(--text-dim)",
                }}
              >
                {m.label}
              </span>
            ))
          )}
        </div>

        {/* Verdict word + conviction arc */}
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className={`leading-[0.95] ${wordSize}`}>
              <Term k={dirKey(live ? read.direction : "long")} bare>
                <VerdictWord
                  word={live ? dirMeta.word : "LONG"}
                  runId={runId}
                  color={live && read.direction === "no_trade" ? "var(--text-mid)" : "var(--ai-gold)"}
                />
              </Term>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <span className="chip">
                {live ? (
                  <Term k="CONVICTION" below>
                    single seat · <span className="text-gold">validated</span>
                  </Term>
                ) : (
                  <Term k="CONSENSUS" below>
                    consensus <span className="text-gold">aligned 3–1</span>
                  </Term>
                )}
              </span>
            </div>
          </div>
          <ConvictionArc
            value={live ? read.conviction / 5 : 0.68}
            label={live ? `${read.conviction}/5` : "68"}
            hue={dirMeta.hue}
            runId={runId}
          />
        </div>

        {/* Plan facts — dot-leader instrument rows */}
        <div className="mt-4 space-y-2 border-t border-hair/60 pt-3.5">
          {live ? (
            <>
              {read.entry_zone && (
                <Row label="entry" term="ENTRY">
                  {formatPrice(read.entry_zone.low)} <span className="text-dim">–</span>{" "}
                  {formatPrice(read.entry_zone.high)}
                </Row>
              )}
              {read.stop_loss && (
                <Row label="stop" term="STOP">
                  <span className="text-bear">{formatPrice(read.stop_loss)}</span>
                </Row>
              )}
              {read.targets.map((t, i) => (
                <Row key={i} label={`tp${i + 1}`} term={i === 0 ? "TARGET" : undefined}>
                  <span className="text-bull">{formatPrice(t.price)}</span>{" "}
                  <span className="text-dim">
                    · <Term k="RR" edge>{t.rr.toFixed(1)}R</Term>
                  </span>
                </Row>
              ))}
              {read.invalidation && (
                <Row label="invalid" term="INVALIDATION">
                  {read.invalidation.condition} {formatPrice(read.invalidation.price)}
                </Row>
              )}
              {read.direction === "no_trade" && (
                <Row label="plan">
                  <span className="text-mid">no trade — capital preserved</span>
                </Row>
              )}
            </>
          ) : (
            <>
              <Row label="entry">
                {formatPrice(demo.entryLow)} <span className="text-dim">–</span>{" "}
                {formatPrice(demo.entryHigh)}
              </Row>
              <Row label="stop">
                <span className="text-bear">{formatPrice(demo.stop)}</span>
              </Row>
              {demo.tps.map((t, i) => (
                <Row key={i} label={`tp${i + 1}`}>
                  <span className="text-bull">{formatPrice(t.px)}</span>{" "}
                  <span className="text-dim">· {t.rr.toFixed(1)}R</span>
                </Row>
              ))}
              <Row label="invalid">below {formatPrice(demo.invalidation)}</Row>
            </>
          )}
        </div>

        {/* Thesis — the desk speaks (C6 voice), always gold; Bengali beneath */}
        <div className="mt-4 border-l-2 border-[rgba(232,197,116,0.35)] pl-3">
          <p className="text-[14px] font-medium leading-relaxed text-gold/90">
            {live
              ? read.thesis
              : "Asia lows swept into 4H demand and reclaimed. We want longs only while the reclaim holds; funding is neutral, so no crowding tax on the trade."}
          </p>
          <p className="font-bn mt-2 text-[12.5px] leading-relaxed text-gold/80">
            {live
              ? read.thesis_bn ??
                "লাইভ রায়টি বাংলায় আসবে — মডেল বাংলা অংশ দিলে এখানে দেখা যাবে।"
              : "এশিয়া সেশনের লো-গুলো সুইপ হয়ে ৪ঘণ্টার ডিমান্ড জোনে ঢুকে আবার উপরে ফিরে এসেছে। যতক্ষণ এই রিক্লেইম টিকে থাকে, আমরা শুধু লং-ই খুঁজব; ফান্ডিং নিউট্রাল, তাই ভিড়ের বাড়তি খরচ নেই।"}
          </p>
        </div>
        <p className="mt-3 text-[11.5px] leading-snug text-mid">
          <span className="text-dim">Fails if:</span>{" "}
          {live
            ? read.failure_mode
            : "reclaim loses on a 1h close — sweep becomes continuation and the pool below is the target."}
        </p>
        <p className="font-bn mt-1.5 text-[12px] leading-relaxed text-mid">
          <span className="text-dim">যেখানে ভুল হবে:</span>{" "}
          {live
            ? read.failure_mode_bn ?? "—"
            : "১ঘণ্টার ক্যান্ডেল রিক্লেইমের নিচে বন্ধ হলে খেলা শেষ — তখন সুইপটাই কন্টিনিউয়েশন হয়ে যায়, আর নিচের পুল-ই পরের টার্গেট।"}
        </p>

        {/* The honesty line — evidence lock status */}
        <p className="mt-3 border-t border-hair/50 pt-2.5 font-mono text-[9.5px] tracking-[0.08em] text-dim">
          {live ? (
            <Term k="EVIDENCE">✓ {read.evidence.length} evidence refs verified against brief</Term>
          ) : data?.status === "degraded" ? (
            <>read dropped: {data.reason ?? "validation failed twice"} — showing demo</>
          ) : (
            <>placeholder — first live read replaces this card</>
          )}
        </p>

        {/* Save this read into the journal (single-user local store for now) */}
        {canSave && (
          <button
            onClick={saveToJournal}
            disabled={saved}
            className="mt-3 w-full rounded-md border border-[rgba(232,197,116,0.3)] py-1.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-gold/90 transition-colors duration-200 hover:bg-[rgba(232,197,116,0.08)] disabled:border-bull/45 disabled:text-bull"
          >
            {saved ? (
              <>✓ saved · <span className="font-bn normal-case">জার্নালে সংরক্ষিত</span></>
            ) : (
              <>＋ save to journal · <span className="font-bn normal-case">জার্নালে যোগ</span></>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
