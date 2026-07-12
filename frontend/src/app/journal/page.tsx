"use client";

/** Journal & analytics (FR-6). Trades saved from the Desk Verdict persist in
 *  localStorage (`dp:journal`, single-user P1). Open trades are AUTO-GRADED
 *  on load (P3 · FR-6): a deterministic backend check (candle-walk, no AI)
 *  looks at what price actually did since the trade was saved and marks tp/sl
 *  if it's since been decided — manual tp/sl/invalidated buttons stay
 *  available as an override. Summary stats are computed LIVE from graded
 *  trades. Grading a CIO-plan trade also reports the outcome to /outcomes
 *  (ADR-0018), and the seat leaderboard + calibration curve render LIVE from
 *  /calibration once any graded outcomes exist (SAMPLE placeholders until
 *  then). Times display in Asia/Dhaka; storage stays UTC (invariant 3).
 */

import { Fragment, useEffect, useMemo, useState } from "react";

import BacktestPanel from "@/components/BacktestPanel";
import PaperDeskPanel from "@/components/PaperDeskPanel";
import SampleTag from "@/components/SampleTag";
import SiteHeader from "@/components/SiteHeader";
import SourceBadge from "@/components/SourceBadge";
import Term from "@/components/Term";
import {
  fetchCalibration,
  fetchGrade,
  fetchLessons,
  fetchLessonTags,
  formatPrice,
  postLesson,
  postOutcome,
  type CalibrationView,
  type LessonsDigest,
} from "@/lib/api";
import {
  computeStats,
  loadJournal,
  markCalPosted,
  patchTrade,
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

function CalibrationCurve({ points = CALIB }: { points?: Array<[number, number]> }) {
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
        points={points.map(([p, a]) => `${x(p).toFixed(1)},${y(a).toFixed(1)}`).join(" ")}
        fill="none" stroke="var(--ai-gold)" strokeWidth="1.5" opacity="0.8"
      />
      {points.map(([p, a]) => (
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

/** Post-mortem editor (ADR-0019) — "why did it fail, what was missing".
 *  Structured tags + a free-text note; saving re-posts the lesson under the
 *  trade's stable closedAt, so refining a reason UPDATES, never duplicates. */
function PostMortemEditor({
  trade,
  tags,
  onSave,
}: {
  trade: JournalTrade;
  tags: Record<string, { en: string; bn: string }>;
  onSave: (tags: string[], note: string) => void;
}) {
  const [picked, setPicked] = useState<string[]>(trade.failureTags ?? []);
  const [note, setNote] = useState(trade.failureNote ?? "");
  const [saved, setSaved] = useState(false);

  const toggle = (k: string) =>
    setPicked((prev) => {
      setSaved(false);
      if (prev.includes(k)) return prev.filter((x) => x !== k);
      return prev.length >= 4 ? prev : [...prev, k];
    });

  return (
    <div className="rounded-[10px] border border-bear/25 bg-abyss/50 px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-bear/80">
          post-mortem — why did it fail?
        </span>
        <span className="bn-sub">কেন হারলো? কী তথ্য ঘাটতি ছিল?</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {Object.entries(tags).map(([k, label]) => (
          <button
            key={k}
            onClick={() => toggle(k)}
            className={`rounded-md border px-2 py-1 text-left font-mono text-[9.5px] transition-colors duration-150 ${
              picked.includes(k)
                ? "border-warn/60 text-warn"
                : "border-hair text-dim hover:text-mid"
            }`}
            title={label.bn}
          >
            {label.en}
          </button>
        ))}
      </div>
      <textarea
        value={note}
        onChange={(e) => {
          setNote(e.target.value.slice(0, 500));
          setSaved(false);
        }}
        rows={2}
        placeholder="What information was missing? What would you check next time? · কী জানা থাকলে এড়ানো যেত?"
        className="mt-2 w-full resize-y rounded-md border border-hair bg-abyss px-2.5 py-1.5 font-sans text-[11.5px] leading-snug text-hi outline-none placeholder:text-dim/70"
      />
      <div className="mt-1.5 flex items-center justify-between">
        <span className="font-mono text-[9px] text-dim">
          feeds the desk&apos;s next synthesis (ADR-0019) · {note.length}/500
        </span>
        <button
          onClick={() => {
            onSave(picked, note.trim());
            setSaved(true);
          }}
          disabled={picked.length === 0 && !note.trim()}
          className={`rounded-md border px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] transition-colors duration-150 ${
            saved
              ? "border-bull/40 text-bull"
              : "border-warn/40 text-warn hover:border-warn/70 disabled:opacity-40"
          }`}
        >
          {saved ? "✓ lesson saved" : "save lesson · শিক্ষা জমা"}
        </button>
      </div>
    </div>
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
  const [cal, setCal] = useState<CalibrationView | null>(null);
  const [lessonsDigest, setLessonsDigest] = useState<LessonsDigest | null>(null);
  const [lessonTags, setLessonTags] = useState<Record<string, { en: string; bn: string }>>({});
  const [pmOpen, setPmOpen] = useState<Set<string>>(new Set());

  useEffect(() => {
    setTrades(loadJournal());
    setReady(true);
    fetchCalibration().then(setCal).catch(() => {}); // analytics enrichment
    fetchLessons().then(setLessonsDigest).catch(() => {});
    fetchLessonTags().then((r) => setLessonTags(r.tags)).catch(() => {});
  }, []);

  // Grade a trade AND, when it's a CIO-plan trade carrying the calibration
  // payload (ADR-0018), report the outcome so the desk learns which seats to
  // trust. `calPosted` + backend idempotency prevent double-counting.
  const grade = (id: string, o: Outcome) => {
    const t = trades.find((x) => x.id === id);
    setTrades(setOutcome(id, o));
    if (!t || t.dir === "no_trade") return;
    // Stamp a stable close time ONCE — it's the idempotency key for both
    // /outcomes and /lessons, so refined post-mortems update, never duplicate.
    const closedAt = t.closedAt ?? new Date().toISOString();
    if (!t.closedAt) setTrades(patchTrade(id, { closedAt }));

    if (
      (o === "tp" || o === "sl") && t.source === "cio" && !t.calPosted &&
      t.confidence != null && t.checklist != null && t.agreement != null
    ) {
      postOutcome({
        symbol: t.symbol,
        direction: t.dir,
        outcome: o,
        confidence: t.confidence,
        checklist: t.checklist,
        agreement: t.agreement,
        seat_votes: t.seatVotes ?? {},
        closed_at: closedAt,
      })
        .then(() => {
          setTrades(markCalPosted(id));
          fetchCalibration().then(setCal).catch(() => {});
        })
        .catch(() => {
          /* backend unreachable — will retry on the next manual grade */
        });
    }

    // Lessons loop (ADR-0019): every graded trade is recorded (wins too, so
    // per-variant win rates are honest). Losses go in tag-less first; the
    // post-mortem editor below re-posts with tags+note (same key → update).
    if (o === "tp" || o === "sl" || o === "invalidated") {
      postLesson({
        symbol: t.symbol,
        source: t.source,
        variant: t.variant ?? null,
        direction: t.dir,
        outcome: o,
        tags: t.failureTags ?? [],
        note: t.failureNote ?? "",
        closed_at: closedAt,
      })
        .then(() => {
          setTrades(patchTrade(id, { lessonPosted: true }));
          fetchLessons().then(setLessonsDigest).catch(() => {});
        })
        .catch(() => {});
    }
  };

  // The post-mortem: why did it fail, what was missing. Re-posts the lesson
  // with tags + note under the SAME closedAt — the backend updates in place.
  const savePostMortem = (id: string, tags: string[], note: string) => {
    const t = trades.find((x) => x.id === id);
    if (!t || t.dir === "no_trade" || !t.closedAt) return;
    if (t.outcome !== "sl" && t.outcome !== "invalidated") return;
    setTrades(patchTrade(id, { failureTags: tags, failureNote: note }));
    postLesson({
      symbol: t.symbol,
      source: t.source,
      variant: t.variant ?? null,
      direction: t.dir,
      outcome: t.outcome,
      tags,
      note,
      closed_at: t.closedAt,
    })
      .then(() => fetchLessons().then(setLessonsDigest).catch(() => {}))
      .catch(() => {});
  };
  const del = (id: string) => setTrades(removeTrade(id));
  const stats = useMemo(() => computeStats(trades), [trades]);

  // Real calibration data (when any outcomes exist) replaces the SAMPLE blocks.
  const calLive = cal != null && cal.n_outcomes > 0;
  const curvePoints = useMemo(() => {
    if (!calLive || !cal) return null;
    const pts = cal.curve
      .filter((b) => b.n > 0 && b.win_rate != null)
      .map((b) => [(b.lo + b.hi) / 2, b.win_rate as number] as [number, number]);
    return pts.length >= 2 ? pts : null;
  }, [cal, calLive]);

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
              <span className="flex items-center gap-1.5">
                <span className="micro-label block">trade log · {trades.length} saved</span>
                <SourceBadge surface="journal" />
              </span>
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
                    const failed = t.outcome === "sl" || t.outcome === "invalidated";
                    const hasReason = (t.failureTags?.length ?? 0) > 0 || !!t.failureNote;
                    return (
                      <Fragment key={t.id}>
                      <tr className="transition-colors duration-150 hover:bg-raised/40">
                        <td className="px-5 py-2.5 tabular-nums text-dim">{fmtDate(t.savedAt)}</td>
                        <td className="px-3 py-2.5 text-hi">
                          {t.symbol.replace("USDT", "")}
                          {t.variant && <span className="ml-1 text-[9px] text-dim">·{t.variant}</span>}
                        </td>
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
                          {failed && (
                            <button
                              onClick={() =>
                                setPmOpen((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(t.id)) next.delete(t.id);
                                  else next.add(t.id);
                                  return next;
                                })
                              }
                              className={`ml-1.5 rounded-md border px-1.5 py-px text-[9.5px] transition-colors duration-150 ${
                                hasReason
                                  ? "border-warn/40 text-warn"
                                  : "border-hair text-dim hover:text-warn"
                              }`}
                              title="record why it failed · কেন হারলো লিখুন"
                            >
                              {hasReason ? "✎ reason" : "why?"}
                            </button>
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
                      {failed && pmOpen.has(t.id) && (
                        <tr>
                          <td colSpan={10} className="px-5 pb-3">
                            <PostMortemEditor
                              trade={t}
                              tags={lessonTags}
                              onSave={(tags, note) => savePostMortem(t.id, tags, note)}
                            />
                          </td>
                        </tr>
                      )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Strategy lessons (ADR-0019) — per-style record + failure patterns.
            This exact digest also rides the CIO's next synthesis input. */}
        {lessonsDigest && lessonsDigest.n_records > 0 && (
          <div className="card dp-rise mt-4" style={{ animationDelay: "270ms" }}>
            <div className="flex items-start justify-between border-b border-hair/70 px-5 py-3">
              <span className="min-w-0">
                <span className="micro-label block">strategy lessons · fed to the cio</span>
                <span className="bn-sub mt-0.5">কৌশলের শিক্ষা — ডেস্ক পরের রায়ে এগুলো পড়ে</span>
              </span>
              <span className="shrink-0 rounded-md border border-hair px-2 py-px font-mono text-[9px] tracking-[0.12em] text-bull">
                LIVE · {lessonsDigest.n_records}
              </span>
            </div>
            <div className="grid gap-x-6 gap-y-3 px-5 py-4 md:grid-cols-2">
              <div>
                <span className="micro-label">per-style record</span>
                <div className="mt-2 space-y-1.5">
                  {Object.entries(lessonsDigest.by_variant)
                    .filter(([, v]) => v.n > 0)
                    .sort(([, a], [, b]) => b.n - a.n)
                    .map(([k, v]) => (
                      <div key={k} className="flex items-center text-[11.5px]">
                        <span className="w-[130px] shrink-0 font-mono text-[10px] uppercase tracking-[0.08em] text-hi">
                          {k.replace("setup:", "")}
                        </span>
                        <span className="leader" />
                        <span
                          className={`font-mono tabular-nums ${
                            v.win_rate == null ? "text-dim" : v.win_rate >= 0.5 ? "text-bull" : "text-bear"
                          }`}
                        >
                          {v.wins}W {v.losses}L
                          {v.win_rate != null
                            ? ` · ${Math.round(v.win_rate * 100)}%`
                            : ` · needs ${3 - v.n} more`}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
              <div>
                <span className="micro-label">recurring failure causes</span>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {lessonsDigest.top_tags.length === 0 && (
                    <span className="text-[11px] text-dim">none recorded yet</span>
                  )}
                  {lessonsDigest.top_tags.map(([tag, count]) => (
                    <span key={tag} className="rounded-md border border-warn/40 px-2 py-1 font-mono text-[9.5px] text-warn">
                      {lessonTags[tag]?.en ?? tag} <span className="text-dim">×{count}</span>
                    </span>
                  ))}
                </div>
                {lessonsDigest.recent_notes.length > 0 && (
                  <div className="mt-3 space-y-1">
                    <span className="micro-label">recent post-mortems</span>
                    {lessonsDigest.recent_notes.slice(0, 4).map((n, i) => (
                      <p key={i} className="text-[10.5px] leading-snug text-dim">▸ {n}</p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Paper desk (P5 · ADR-0021) — the approval gate's home: the AI can
            only propose; these approve/reject buttons are the sole fill path. */}
        <PaperDeskPanel />

        {/* Backtest (P5 · ADR-0020) — walk-forward replay of the setup rules
            over real history; the sanctioned evidence for tuning ADR-0019's
            multiplier table. Engine surface, never gold. */}
        <BacktestPanel />

        {/* Leaderboard + calibration — LIVE from /calibration once graded
            CIO-plan outcomes exist (ADR-0018); SAMPLE placeholders until then */}
        <div className="mt-4 grid gap-4 pb-8 lg:grid-cols-2">
          <div className="card card-ai dp-rise" style={{ animationDelay: "300ms" }}>
            <div className="flex items-start justify-between border-b border-[rgba(232,197,116,0.18)] px-5 py-3">
              <span className="min-w-0">
                <span className="micro-label block" style={{ color: "var(--ai-gold)", opacity: 0.9 }}>
                  seat leaderboard · feeds cio weighting
                </span>
                <span className="bn-sub mt-0.5">বিশ্লেষক-সিটের পারফরম্যান্স</span>
              </span>
              {calLive ? (
                <span className="rounded-md border border-[rgba(232,197,116,0.4)] px-2 py-px font-mono text-[9px] tracking-[0.12em] text-gold">
                  LIVE · {cal!.n_outcomes}
                </span>
              ) : (
                <SampleTag />
              )}
            </div>
            <div className="space-y-3.5 px-5 py-4">
              {calLive && cal
                ? Object.entries(cal.seats).map(([m, s]) => (
                    <div key={m}>
                      <div className="flex items-baseline justify-between text-[11.5px]">
                        <span className="font-mono uppercase tracking-[0.1em] text-hi">{m}</span>
                        <span className="font-mono tabular-nums text-gold">
                          ×{s.weight.toFixed(2)}{" "}
                          <span className="text-dim">
                            · {(s.accuracy * 100).toFixed(0)}% acc · n {s.eff_n.toFixed(1)}
                          </span>
                        </span>
                      </div>
                      {/* weight bar: 0.6 (floor) .. 1.4 (cap); 1.0 = neutral */}
                      <div className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-raised">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${(s.weight / 1.4) * 100}%`,
                            background: "var(--ai-gold)",
                            opacity: 0.75,
                          }}
                        />
                      </div>
                    </div>
                  ))
                : SEATS.map((s) => (
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
              {calLive && cal && (
                <p className="pt-1 font-mono text-[9.5px] tabular-nums text-dim">
                  blend: facts {Math.round(cal.blend_w * 100)}% / desk {Math.round((1 - cal.blend_w) * 100)}%
                  {cal.blend_active ? "" : " · frozen until 10 effective outcomes"}
                  {cal.brier_blended != null ? ` · brier ${cal.brier_blended.toFixed(3)}` : ""}
                </p>
              )}
              <p className="pt-1 text-[10.5px] leading-snug text-dim">
                Seat weight ×0.6–×1.4 — graded hits vs misses, recency-decayed, shrunk toward
                neutral on small samples (ADR-0018). Weights adjust confidence only, never direction.
              </p>
            </div>
          </div>

          <div className="card dp-rise" style={{ animationDelay: "360ms" }}>
            <div className="flex items-start justify-between border-b border-hair/70 px-5 py-3">
              <span className="min-w-0">
                <span className="micro-label block">confidence calibration</span>
                <span className="bn-sub mt-0.5">আত্মবিশ্বাস বনাম বাস্তব ফল</span>
              </span>
              {curvePoints ? (
                <span className="rounded-md border border-hair px-2 py-px font-mono text-[9px] tracking-[0.12em] text-bull">
                  LIVE
                </span>
              ) : (
                <SampleTag />
              )}
            </div>
            <div className="flex items-center justify-between gap-4 px-5 py-4">
              <CalibrationCurve points={curvePoints ?? undefined} />
              <p className="max-w-[180px] text-[10.5px] leading-snug text-dim">
                Dots on the dashed line = published confidence matches reality. Above:
                underconfident. Below: overconfident — every graded outcome re-fits the
                blend automatically (ADR-0018).
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
