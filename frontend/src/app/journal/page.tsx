"use client";

/** Journal & analytics (FR-6). Trades saved from the Desk Verdict persist in
 *  localStorage (`dp:journal`, single-user P1). Open trades are AUTO-GRADED
 *  on load (P3 · FR-6): a deterministic backend check (candle-walk, no AI)
 *  looks at what price actually did since the trade was saved and marks tp/sl
 *  if it's since been decided — manual tp/sl/invalidated buttons stay
 *  available as an override. Summary stats are computed LIVE from graded
 *  trades. The seat leaderboard + calibration curve stay SAMPLE until Fable
 *  wires the calibration formula (§F5). Times display in Asia/Dhaka; storage
 *  stays UTC (invariant 3).
 */

import { useEffect, useMemo, useState } from "react";

import SampleTag from "@/components/SampleTag";
import SiteHeader from "@/components/SiteHeader";
import Term from "@/components/Term";
import { fetchGrade, formatPrice } from "@/lib/api";
import {
  computeStats,
  loadJournal,
  removeTrade,
  setOutcome,
  tradeR,
  type JournalTrade,
  type Outcome,
} from "@/lib/journal";
import { dirKey } from "@/lib/terms";

// ── SAMPLE analytics (P3 wires real model_scores + calibration) ──
const SEATS = [
  { seat: "TREND", model: "deepseek-v3", acc: 0.64, weight: 0.31 },
  { seat: "DERIV", model: "qwen2.5-72b", acc: 0.61, weight: 0.27 },
  { seat: "RISK", model: "gemini-flash", acc: 0.57, weight: 0.24 },
  { seat: "CNTRN", model: "llama-3.3-70b", acc: 0.49, weight: 0.18 },
];
const CALIB: Array<[number, number]> = [
  [0.52, 0.46],
  [0.58, 0.55],
  [0.65, 0.61],
  [0.72, 0.78],
  [0.8, 0.74],
];

const outcomeStyle: Record<Outcome, string> = {
  tp: "text-bull border-bull/40",
  sl: "text-bear border-bear/40",
  invalidated: "text-dim border-hair",
  open: "text-pulse border-pulse/40",
};
const outcomeBn: Record<Outcome, string> = {
  tp: "লাভে বন্ধ",
  sl: "স্টপে বন্ধ",
  invalidated: "বাতিল",
  open: "চলমান",
};

const dhakaDate = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka",
  day: "2-digit",
  month: "short",
});
function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : dhakaDate.format(d);
}

function toneClass(t?: string) {
  return t === "bull" ? "text-bull" : t === "bear" ? "text-bear" : t === "gold" ? "text-gold" : "text-hi";
}

function CalibrationCurve() {
  const W = 220;
  const H = 130;
  const PAD = 14;
  const x = (v: number) => PAD + (v - 0.4) * ((W - 2 * PAD) / 0.5);
  const y = (v: number) => H - PAD - (v - 0.4) * ((H - 2 * PAD) / 0.5);
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-label="Calibration curve" className="max-w-full">
      <line
        x1={x(0.42)} y1={y(0.42)} x2={x(0.88)} y2={y(0.88)}
        stroke="var(--text-dim)" strokeWidth="1" strokeDasharray="3 4" opacity="0.5"
      />
      <polyline
        points={CALIB.map(([p, a]) => `${x(p).toFixed(1)},${y(a).toFixed(1)}`).join(" ")}
        fill="none" stroke="var(--ai-gold)" strokeWidth="1.5" opacity="0.8"
      />
      {CALIB.map(([p, a]) => (
        <circle key={p} cx={x(p)} cy={y(a)} r="3" fill="var(--ai-gold)" />
      ))}
      <text x={W - PAD} y={H - 3} textAnchor="end" fontSize="8" fill="var(--text-dim)"
        fontFamily="var(--font-geist-mono), monospace" letterSpacing="0.1em">
        PREDICTED →
      </text>
      <text x={4} y={PAD} fontSize="8" fill="var(--text-dim)"
        fontFamily="var(--font-geist-mono), monospace" letterSpacing="0.1em">
        ↑ REALIZED
      </text>
    </svg>
  );
}

function GradeButton({
  label,
  tone,
  onClick,
}: {
  label: string;
  tone: "bull" | "bear" | "dim";
  onClick: () => void;
}) {
  const cls =
    tone === "bull"
      ? "border-bull/40 text-bull hover:bg-bull/10"
      : tone === "bear"
        ? "border-bear/40 text-bear hover:bg-bear/10"
        : "border-hair text-dim hover:text-mid";
  return (
    <button
      onClick={onClick}
      className={`rounded-md border px-1.5 py-px font-mono text-[9.5px] uppercase tracking-[0.06em] transition-colors duration-150 ${cls}`}
    >
      {label}
    </button>
  );
}

export default function JournalPage() {
  const [trades, setTrades] = useState<JournalTrade[]>([]);
  const [ready, setReady] = useState(false);
  const [checking, setChecking] = useState<Set<string>>(new Set());

  useEffect(() => {
    setTrades(loadJournal());
    setReady(true);
  }, []);

  const grade = (id: string, o: Outcome) => setTrades(setOutcome(id, o));
  const del = (id: string) => setTrades(removeTrade(id));
  const stats = useMemo(() => computeStats(trades), [trades]);

  // Auto-grade (P3 · FR-6): once, on load, check every OPEN trade against
  // what price actually did since it was saved — a deterministic candle-walk,
  // no AI. "invalidated" stays a human judgment call (the setup broke down
  // isn't purely a price fact) and is never set automatically.
  useEffect(() => {
    if (!ready) return;
    const open = trades.filter(
      (t): t is JournalTrade & { dir: "long" | "short"; stop: string; target: string } =>
        t.outcome === "open" && t.dir !== "no_trade" && !!t.stop && !!t.target,
    );
    if (!open.length) return;
    setChecking(new Set(open.map((t) => t.id)));
    open.forEach((t) => {
      fetchGrade(t.symbol, t.dir, t.stop, t.target, t.savedAt)
        .then((res) => {
          if (res.outcome !== "open") grade(t.id, res.outcome);
        })
        .catch(() => {
          /* backend unreachable or rate-limited — stays open, retried next visit */
        })
        .finally(() => {
          setChecking((prev) => {
            const next = new Set(prev);
            next.delete(t.id);
            return next;
          });
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  const entryText = (t: JournalTrade) => {
    if (!t.entryLow) return "—";
    return t.entryHigh && t.entryHigh !== t.entryLow
      ? `${formatPrice(t.entryLow)}–${formatPrice(t.entryHigh)}`
      : formatPrice(t.entryLow);
  };

  const STAT_TILES = [
    {
      label: "win rate · graded",
      bn: "উইন রেট",
      value: stats.winRatePct == null ? "—" : `${stats.winRatePct.toFixed(0)}%`,
      tone: stats.winRatePct == null ? "gold" : stats.winRatePct >= 50 ? "bull" : "bear",
    },
    {
      label: "avg R · graded",
      bn: "গড় R",
      value: stats.avgR == null ? "—" : `${stats.avgR >= 0 ? "+" : ""}${stats.avgR.toFixed(2)}R`,
      tone: stats.avgR == null ? "gold" : stats.avgR >= 0 ? "bull" : "bear",
    },
    {
      label: "total R",
      bn: "মোট R",
      value: stats.totalR == null ? "—" : `${stats.totalR >= 0 ? "+" : ""}${stats.totalR.toFixed(1)}R`,
      tone: "gold",
    },
    { label: "trades · open", bn: "ট্রেড · চলমান", value: `${stats.total} · ${stats.open}`, tone: "gold" },
  ];

  return (
    <main className="flex min-h-screen flex-col">
      <SiteHeader />

      <div className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 sm:px-6">
        <div className="mb-5">
          <h1 className="text-[28px] font-bold tracking-tight text-hi">
            Journal <span className="text-gold">&amp; grading</span>
          </h1>
          <span className="bn-sub mt-0.5">ট্রেড খাতা ও মূল্যায়ন — ডেস্ক থেকে সেভ করা রায়, নিজে গ্রেড করুন</span>
        </div>

        {/* Summary tiles — live from graded trades */}
        <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
          {STAT_TILES.map((s, i) => (
            <div key={s.label} className="card dp-rise px-5 py-4" style={{ animationDelay: `${i * 60}ms` }}>
              <div className={`font-mono text-[26px] font-light tabular-nums ${toneClass(s.tone)}`}>{s.value}</div>
              <div className="micro-label mt-1.5">{s.label}</div>
              <div className="bn-sub mt-0.5">{s.bn}</div>
            </div>
          ))}
        </div>

        {/* Trade log — real saved reads */}
        <div className="card dp-rise mt-4 overflow-hidden" style={{ animationDelay: "240ms" }}>
          <div className="flex items-center justify-between border-b border-hair/70 px-5 py-3">
            <span className="min-w-0">
              <span className="micro-label block">trade log · {trades.length} saved</span>
              <span className="bn-sub mt-0.5">সেভ করা ট্রেড — খোলা ট্রেড গ্রেড করুন বা মুছুন</span>
            </span>
            <span className="micro-label hidden sm:block">graded as published — never edited</span>
          </div>

          {ready && trades.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <div className="text-[14px] text-mid">No trades yet.</div>
              <div className="font-bn mt-1 text-[12.5px] text-dim">
                ডেস্কের রায় কার্ড থেকে “save to journal” চাপলে ট্রেড এখানে জমা হবে।
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-[12px]">
                <thead>
                  <tr className="border-b border-hair/50 text-[9.5px] uppercase tracking-[0.14em] text-dim">
                    <th className="px-5 py-2.5 font-medium">date</th>
                    <th className="px-3 py-2.5 font-medium">symbol</th>
                    <th className="px-3 py-2.5 font-medium">dir</th>
                    <th className="px-3 py-2.5 text-right font-medium"><Term k="CONVICTION">conv</Term></th>
                    <th className="px-3 py-2.5 text-right font-medium"><Term k="ENTRY">entry</Term></th>
                    <th className="px-3 py-2.5 text-right font-medium"><Term k="STOP">stop</Term></th>
                    <th className="px-3 py-2.5 text-right font-medium"><Term k="TARGET">tp1</Term></th>
                    <th className="px-3 py-2.5 text-right font-medium"><Term k="RR">r</Term></th>
                    <th className="px-3 py-2.5 font-medium">status</th>
                    <th className="px-5 py-2.5 text-right font-medium">grade / delete</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hair/40 font-mono">
                  {trades.map((t) => {
                    const r = tradeR(t);
                    return (
                      <tr key={t.id} className="transition-colors duration-150 hover:bg-raised/40">
                        <td className="px-5 py-2.5 tabular-nums text-dim">{fmtDate(t.savedAt)}</td>
                        <td className="px-3 py-2.5 text-hi">{t.symbol.replace("USDT", "")}</td>
                        <td className={`px-3 py-2.5 ${t.dir === "long" ? "text-bull" : t.dir === "short" ? "text-bear" : "text-mid"}`}>
                          <Term k={dirKey(t.dir)} bare>
                            {t.dir === "long" ? "▲ long" : t.dir === "short" ? "▼ short" : "◆ —"}
                          </Term>
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-gold/90">{t.conviction}/5</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-mid">{entryText(t)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-bear/90">{t.stop ? formatPrice(t.stop) : "—"}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-bull/90">{t.target ? formatPrice(t.target) : "—"}</td>
                        <td className={`px-3 py-2.5 text-right tabular-nums ${r == null ? "text-dim" : r >= 0 ? "text-bull" : "text-bear"}`}>
                          {r == null ? "—" : `${r > 0 ? "+" : ""}${r.toFixed(1)}R`}
                        </td>
                        <td className="px-3 py-2.5">
                          <span
                            className={`inline-block rounded-md border px-2 py-px text-[10px] ${outcomeStyle[t.outcome]}`}
                            title={outcomeBn[t.outcome]}
                          >
                            {t.outcome}
                          </span>
                          {checking.has(t.id) && (
                            <span className="ml-1.5 font-mono text-[9.5px] text-dim" title="দাম যাচাই হচ্ছে">
                              checking…
                            </span>
                          )}
                        </td>
                        <td className="px-5 py-2.5">
                          <div className="flex items-center justify-end gap-1.5">
                            {t.outcome === "open" ? (
                              <>
                                <GradeButton label="tp" tone="bull" onClick={() => grade(t.id, "tp")} />
                                <GradeButton label="sl" tone="bear" onClick={() => grade(t.id, "sl")} />
                                <GradeButton label="inval" tone="dim" onClick={() => grade(t.id, "invalidated")} />
                              </>
                            ) : (
                              <GradeButton label="reopen" tone="dim" onClick={() => grade(t.id, "open")} />
                            )}
                            <button
                              onClick={() => del(t.id)}
                              className="ml-1 rounded-md border border-hair px-1.5 py-px font-mono text-[11px] leading-none text-dim transition-colors duration-150 hover:border-bear/40 hover:text-bear"
                              title="delete trade · মুছুন"
                              aria-label="delete trade"
                            >
                              ×
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Leaderboard + calibration — SAMPLE until P3 grading */}
        <div className="mt-4 grid gap-4 pb-8 lg:grid-cols-2">
          <div className="card card-ai dp-rise" style={{ animationDelay: "300ms" }}>
            <div className="flex items-start justify-between border-b border-[rgba(232,197,116,0.18)] px-5 py-3">
              <span className="min-w-0">
                <span className="micro-label block" style={{ color: "var(--ai-gold)", opacity: 0.9 }}>
                  seat leaderboard · feeds cio weighting
                </span>
                <span className="bn-sub mt-0.5">বিশ্লেষক-সিটের পারফরম্যান্স</span>
              </span>
              <SampleTag />
            </div>
            <div className="space-y-3.5 px-5 py-4">
              {SEATS.map((s) => (
                <div key={s.seat}>
                  <div className="flex items-baseline justify-between text-[11.5px]">
                    <span className="font-mono tracking-[0.1em] text-hi">
                      {s.seat} <span className="text-dim">· {s.model}</span>
                    </span>
                    <span className="font-mono tabular-nums text-gold">{(s.acc * 100).toFixed(0)}% acc</span>
                  </div>
                  <div className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-raised">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${s.weight * 200}%`, maxWidth: "100%", background: "var(--ai-gold)", opacity: 0.75 }}
                    />
                  </div>
                </div>
              ))}
              <p className="pt-1 text-[10.5px] leading-snug text-dim">
                Seat weight = graded accuracy blended with calibration (ADR-0007). A cold seat loses the CIO&apos;s ear before it loses you money.
              </p>
            </div>
          </div>

          <div className="card dp-rise" style={{ animationDelay: "360ms" }}>
            <div className="flex items-start justify-between border-b border-hair/70 px-5 py-3">
              <span className="min-w-0">
                <span className="micro-label block">confidence calibration</span>
                <span className="bn-sub mt-0.5">আত্মবিশ্বাস বনাম বাস্তব ফল</span>
              </span>
              <SampleTag />
            </div>
            <div className="flex items-center justify-between gap-4 px-5 py-4">
              <CalibrationCurve />
              <p className="max-w-[180px] text-[10.5px] leading-snug text-dim">
                Dots on the dashed line = published confidence matches reality. Above: underconfident. Below: overconfident — the blend recalibrates monthly.
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
