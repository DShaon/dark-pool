"use client";

/** Full Desk overlay (P2/P3) — the mandate-analyst panel + the CIO verdict.
 *  Shows each surviving analyst's evidence-locked read (bilingual), the raw
 *  direction tally, the seats that dropped and why — and the desk's ONE
 *  synthesized TradePlan (§B5 · ADR-0015): divergence-classified consensus,
 *  ADR-0007 calibrated confidence, guard-railed levels, risk-based sizing.
 *  Graceful when the free providers are rate-limited: it explains the
 *  degradation instead of breaking.
 */

import { useEffect, useState } from "react";

import SourceBadge from "@/components/SourceBadge";
import Term from "@/components/Term";
import {
  fetchPlan,
  formatPrice,
  proposeOrder,
  type AnalystThesis,
  type DeskPanelResponse,
  type Mandate,
  type TradePlan,
} from "@/lib/api";
import { addTrade } from "@/lib/journal";
import { dirKey } from "@/lib/terms";
import { dhakaTime } from "@/lib/time";

const MANDATE_META: Record<Mandate, { label: string; role: string; bn: string }> = {
  trend: { label: "TREND", role: "continuation case", bn: "ধারাবাহিকতার পক্ষে" },
  contrarian: { label: "CONTRARIAN", role: "reversal case", bn: "উল্টো দিকের পক্ষে" },
  derivatives: { label: "DERIVATIVES", role: "positioning read", bn: "পজিশন-পাঠ" },
  risk: { label: "RISK OFFICER", role: "the case for no trade", bn: "ঝুঁকি-নিয়ন্ত্রণ" },
};

const DIR: Record<string, { word: string; arrow: string }> = {
  long: { word: "LONG", arrow: "▲" },
  short: { word: "SHORT", arrow: "▼" },
  no_trade: { word: "STAND ASIDE", arrow: "◆" },
};

const CONSENSUS_META: Record<string, { label: string; bn: string; tone: string }> = {
  aligned: { label: "ALIGNED", bn: "ঐকমত্য", tone: "text-bull" },
  split: { label: "SPLIT", bn: "বিভক্ত", tone: "text-warn" },
  contested: { label: "CONTESTED", bn: "দ্বিমত", tone: "text-bear" },
};

/** The desk's one call — gold (AI judgment), levels in dot-leader rows,
 *  confidence shown WITH its two formula halves (NFR-7: auditable). */
function CIOVerdict({ plan }: { plan: TradePlan }) {
  const dir = DIR[plan.direction];
  const consensus = CONSENSUS_META[plan.consensus_state];
  const conf = Math.round(plan.confidence.value * 100);
  const isTrade = plan.direction !== "no_trade";
  const [saved, setSaved] = useState(false);
  const [proposed, setProposed] = useState<"idle" | "busy" | "done" | "error">("idle");

  // Save the plan as an OPEN journal trade, carrying the calibration payload
  // (ADR-0018): once graded, the journal reports the outcome to /outcomes and
  // the desk learns which seats to trust.
  const saveToJournal = () => {
    if (saved || !isTrade || !plan.entry_zone || !plan.stop_loss) return;
    addTrade({
      symbol: plan.symbol,
      dir: plan.direction,
      conviction: Math.min(5, Math.max(1, Math.round(plan.confidence.value * 5))),
      entryLow: plan.entry_zone.low,
      entryHigh: plan.entry_zone.high,
      stop: plan.stop_loss,
      target: plan.targets[0]?.price ?? null,
      targetRR: plan.targets[0]?.rr ?? null,
      thesis: plan.thesis,
      source: "cio",
      confidence: plan.confidence.value,
      checklist: plan.confidence.checklist,
      agreement: plan.confidence.agreement,
      seatVotes: plan.divergence.votes_by_seat,
    });
    setSaved(true);
  };

  // Send the plan to the paper desk as an ORDER PROPOSAL (ADR-0021). It sits
  // pending until approved on the journal page — proposing fills nothing.
  const proposeToPaperDesk = async () => {
    if (proposed !== "idle" || !isTrade || !plan.entry_zone || !plan.stop_loss) return;
    if (plan.direction !== "long" && plan.direction !== "short") return;
    setProposed("busy");
    try {
      await proposeOrder({
        symbol: plan.symbol,
        direction: plan.direction,
        entry_low: plan.entry_zone.low,
        entry_high: plan.entry_zone.high,
        stop: plan.stop_loss,
        targets: plan.targets.map((t) => t.price),
        thesis: plan.thesis.slice(0, 600),
      });
      setProposed("done");
    } catch {
      setProposed("error");
    }
  };
  return (
    <div className="mt-3.5 rounded-[10px] border border-[rgba(232,197,116,0.35)] bg-abyss/60 px-4 py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.14em] text-gold/70">
            CIO verdict · <span className="text-dim">{plan.synthesizer}</span>
            <SourceBadge surface="cio" detail={plan.synthesizer} />
          </div>
          <div className="mt-0.5 text-[26px] font-bold leading-tight tracking-tight text-gold">
            <Term k={dirKey(plan.direction)} bare>
              {dir.arrow} {dir.word}
            </Term>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className={`rounded-md border border-hair px-2 py-px font-mono text-[9.5px] tracking-[0.1em] ${consensus.tone}`}>
              {consensus.label} <span className="font-bn text-dim">· {consensus.bn}</span>
            </span>
            {plan.divergence.notes[0] && (
              <span className="font-mono text-[9px] text-dim">{plan.divergence.notes[0]}</span>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-[24px] font-light tabular-nums text-gold">{conf}%</div>
          <div className="micro-label mt-0.5">
            <Term k="CONFIDENCE">confidence</Term>
          </div>
          <div className="mt-0.5 font-mono text-[8.5px] tabular-nums text-dim">
            facts {Math.round(plan.confidence.checklist * 100)} · desk {Math.round(plan.confidence.agreement * 100)}
          </div>
        </div>
      </div>

      {isTrade && plan.entry_zone && (
        <div className="mt-3 grid gap-x-6 gap-y-1 border-t border-[rgba(232,197,116,0.15)] pt-2.5 sm:grid-cols-2">
          <MiniRow label="entry" term="ENTRY" tone="text-hi">
            {formatPrice(plan.entry_zone.low)} <span className="text-dim">–</span> {formatPrice(plan.entry_zone.high)}
          </MiniRow>
          {plan.stop_loss && (
            <MiniRow label="stop" term="STOP" tone="text-bear">
              {formatPrice(plan.stop_loss)}
            </MiniRow>
          )}
          {plan.targets.map((t, i) => (
            <MiniRow key={i} label={`tp${i + 1}`} term="TARGET" tone="text-bull">
              {formatPrice(t.price)} <span className="text-dim">· {t.rr.toFixed(2)}R</span>
            </MiniRow>
          ))}
          {plan.sizing && (
            <MiniRow label="size" term="ENTRY" tone="text-hi">
              {plan.sizing.position_pct.toFixed(1)}%{" "}
              <span className="text-dim">
                of acct · risk {plan.sizing.risk_pct}%{plan.sizing.capped ? " · capped" : ""}
              </span>
            </MiniRow>
          )}
        </div>
      )}

      {plan.confirmation.length > 0 && (
        <div className="mt-2 font-mono text-[9.5px] leading-relaxed text-mid">
          {plan.confirmation.map((c, i) => (
            <div key={i}>▸ {c}</div>
          ))}
        </div>
      )}

      <p className="mt-2.5 text-[12.5px] leading-snug text-gold/95">{plan.thesis}</p>
      {plan.thesis_bn && (
        <p className="font-bn mt-1 text-[11.5px] leading-relaxed text-gold/75">{plan.thesis_bn}</p>
      )}
      <div className="mt-2 space-y-0.5 text-[10.5px] leading-snug text-dim">
        <div>
          <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-bear/80">kills it</span>{" "}
          {plan.failure_mode}
        </div>
        <div>
          <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-warn/80">alt</span>{" "}
          {plan.alternative_scenario}
        </div>
        {plan.invalidation && (
          <div>
            <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-dim">invalid</span>{" "}
            {formatPrice(plan.invalidation.price)} — {plan.invalidation.condition}
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="font-mono text-[8.5px] tracking-[0.08em] text-dim">
          built from {plan.built_from.join(" + ") || "panel"} · ✓ {plan.evidence.length} evidence refs
          {plan.confidence.calibrated
            ? ` · calibrated (facts ${Math.round(plan.confidence.blend_w * 100)}%)`
            : " · uncalibrated (no graded outcomes yet)"}{" "}
          · advisory only
        </p>
        {isTrade && plan.entry_zone && plan.stop_loss && (
          <span className="ml-auto flex flex-wrap gap-2">
            <button
              onClick={() => void proposeToPaperDesk()}
              disabled={proposed === "busy" || proposed === "done"}
              className={`rounded-md border px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] transition-colors duration-150 ${
                proposed === "done"
                  ? "border-bull/40 text-bull"
                  : proposed === "error"
                    ? "border-bear/40 text-bear"
                    : "border-[rgba(232,197,116,0.4)] text-gold/90 hover:border-gold/70"
              }`}
              title="creates a PENDING paper order — you approve it on the journal page; nothing fills without your click (ADR-0021)"
            >
              {proposed === "done"
                ? "✓ proposed · approve in journal"
                : proposed === "error"
                  ? "✕ propose failed — retry"
                  : "◇ propose · paper desk"}
            </button>
            <button
              onClick={saveToJournal}
              disabled={saved}
              className={`rounded-md border px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] transition-colors duration-150 ${
                saved
                  ? "border-bull/40 text-bull"
                  : "border-[rgba(232,197,116,0.4)] text-gold/90 hover:border-gold/70"
              }`}
            >
              {saved ? "✓ saved · journal" : "＋ save to journal · জার্নালে যোগ"}
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

function MiniRow({
  label,
  term,
  tone,
  children,
}: {
  label: string;
  term: "ENTRY" | "STOP" | "TARGET";
  tone: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center text-[11.5px]">
      <span className="w-12 shrink-0 font-mono text-[9.5px] font-medium uppercase tracking-[0.08em] text-mid">
        <Term k={term}>{label}</Term>
      </span>
      <span className="leader" />
      <span className={`font-mono tabular-nums ${tone}`}>{children}</span>
    </div>
  );
}

function AnalystCard({ thesis }: { thesis: AnalystThesis }) {
  const m = MANDATE_META[thesis.mandate];
  const r = thesis.read;
  const dir = DIR[r.direction];
  const isTrade = r.direction !== "no_trade";
  return (
    <div className="dp-rise rounded-[10px] border border-[rgba(232,197,116,0.2)] bg-abyss/40 px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-mono text-[10px] tracking-[0.12em] text-gold/90">{m.label}</div>
          <div className="text-[10px] text-dim">{m.role}</div>
          <div className="bn-sub mt-0.5">{m.bn}</div>
          <div className="mt-0.5 truncate font-mono text-[8.5px] text-dim">{thesis.model_id}</div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-[15px] font-bold text-gold">
            <Term k={dirKey(r.direction)} bare>
              {dir.arrow} {dir.word}
            </Term>
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-dim">
            <Term k="CONVICTION">conv {r.conviction}/5</Term>
          </div>
        </div>
      </div>

      {isTrade && (
        <div className="mt-2 space-y-1 border-t border-hair/50 pt-2">
          {r.entry_zone && (
            <MiniRow label="entry" term="ENTRY" tone="text-hi">
              {formatPrice(r.entry_zone.low)} <span className="text-dim">–</span> {formatPrice(r.entry_zone.high)}
            </MiniRow>
          )}
          {r.stop_loss && (
            <MiniRow label="stop" term="STOP" tone="text-bear">
              {formatPrice(r.stop_loss)}
            </MiniRow>
          )}
          {r.targets[0] && (
            <MiniRow label="tp1" term="TARGET" tone="text-bull">
              {formatPrice(r.targets[0].price)} <span className="text-dim">· {r.targets[0].rr.toFixed(1)}R</span>
            </MiniRow>
          )}
        </div>
      )}

      <p className="mt-2 text-[12px] leading-snug text-gold/90">{r.thesis}</p>
      {r.thesis_bn && <p className="font-bn mt-1 text-[11.5px] leading-relaxed text-gold/75">{r.thesis_bn}</p>}
      <p className="mt-1.5 font-mono text-[9px] tracking-[0.08em] text-dim">
        <Term k="EVIDENCE">✓ {r.evidence.length} evidence refs</Term>
      </p>
    </div>
  );
}

export default function FullDeskPanel({
  open,
  onClose,
  symbol,
  data,
  running,
  onRun,
}: {
  open: boolean;
  onClose: () => void;
  symbol: string;
  data: DeskPanelResponse | null;
  running: boolean;
  onRun: () => void;
}) {
  const [plan, setPlan] = useState<TradePlan | null>(null);
  const [planState, setPlanState] = useState<"idle" | "loading" | "degraded">("idle");

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // The CIO synthesizes once per desk run: keyed on generated_at, so a ⟳
  // re-run (new timestamp) triggers a fresh synthesis while the same cached
  // panel reuses the cached plan (no double model spend).
  const deskRunAt = data?.generated_at;
  const surviving = data?.theses.length ?? 0;
  useEffect(() => {
    setPlan(null);
    if (!open || !deskRunAt || surviving < 2) {
      setPlanState("idle");
      return;
    }
    let stale = false;
    setPlanState("loading");
    fetchPlan(symbol)
      .then((r) => {
        if (stale) return;
        setPlan(r.plan);
        setPlanState(r.plan ? "idle" : "degraded");
      })
      .catch(() => {
        if (!stale) setPlanState("degraded");
      });
    return () => {
      stale = true;
    };
  }, [open, deskRunAt, surviving, symbol]);

  if (!open) return null;

  const theses = data?.theses ?? [];
  const dropped = data?.dropped ?? [];
  const tally = data?.tally ?? {};

  return (
    <div className="fixed inset-0 z-[80]">
      <div className="palette-backdrop absolute inset-0" onClick={onClose} />
      <div className="pointer-events-none absolute inset-0 flex items-start justify-center overflow-y-auto p-4 sm:p-6">
        <div
          className="overlay-card card card-ai glow-ai pointer-events-auto relative my-auto w-full max-w-[880px] overflow-hidden"
          role="dialog"
          aria-modal="true"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-3 border-b border-[rgba(232,197,116,0.18)] px-5 py-3.5">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[18px] font-bold tracking-tight text-gold">
                Full Desk <span className="text-hi">· {symbol}</span>
                <SourceBadge surface="desk" className="text-[13px]" />
              </div>
              <div className="bn-sub mt-0.5">পূর্ণ ডেস্ক · চার বিশ্লেষকের প্যানেল</div>
            </div>
            <div className="flex shrink-0 items-center gap-2.5">
              {data && (
                <span
                  className="rounded-md border px-2 py-px font-mono text-[9.5px] tracking-[0.12em]"
                  style={{
                    borderColor: data.status === "ok" ? "rgba(232,197,116,0.4)" : "var(--line-hair)",
                    color: data.status === "ok" ? "var(--ai-gold)" : "var(--text-dim)",
                  }}
                >
                  {data.status.toUpperCase()}
                </span>
              )}
              <button
                onClick={onRun}
                disabled={running}
                className="font-mono text-[13px] text-dim transition-colors duration-200 hover:text-gold disabled:opacity-40"
                title="re-run the desk"
                aria-label="re-run"
              >
                ⟳
              </button>
              <button
                onClick={onClose}
                className="font-mono text-[15px] leading-none text-dim transition-colors duration-200 hover:text-hi"
                aria-label="close"
              >
                ×
              </button>
            </div>
          </div>

          <div className="px-5 py-4">
            {/* Tally + CIO status */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="micro-label">reads</span>
              {(["long", "short", "no_trade"] as const).map((d) => (
                <span
                  key={d}
                  className="rounded-md border border-hair px-2 py-px font-mono text-[10.5px] tabular-nums text-mid"
                >
                  {d === "no_trade" ? "NO TRADE" : DIR[d].word}{" "}
                  <span className="text-gold">{tally[d] ?? 0}</span>
                </span>
              ))}
              {planState === "loading" && (
                <span className="ml-auto rounded-md border border-[rgba(232,197,116,0.3)] px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-gold/80">
                  CIO synthesizing…
                </span>
              )}
              {planState === "degraded" && (
                <span className="ml-auto rounded-md border border-hair px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-dim">
                  CIO verdict unavailable
                </span>
              )}
              {surviving > 0 && surviving < 2 && (
                <span className="ml-auto rounded-md border border-hair px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-dim">
                  need 2+ seats for a verdict
                </span>
              )}
            </div>

            {/* The desk's one call */}
            {plan && <CIOVerdict plan={plan} />}

            {/* Body states */}
            {theses.length > 0 ? (
              <div className="mt-3.5 grid gap-3 lg:grid-cols-2">
                {theses.map((t) => (
                  <AnalystCard key={t.mandate} thesis={t} />
                ))}
              </div>
            ) : running ? (
              <div className="py-10 text-center">
                <div className="text-[13px] text-mid">Running the desk… four analysts, in parallel.</div>
                <div className="font-bn mt-1 text-[12px] text-dim">চার বিশ্লেষক একসাথে ব্রিফ পড়ছেন…</div>
              </div>
            ) : (
              <div className="mt-3 rounded-[10px] border border-hair bg-abyss/40 px-5 py-8 text-center">
                <div className="text-[13px] text-mid">No analyst survived this run.</div>
                <div className="font-bn mt-1 text-[12px] text-dim">
                  এই মুহূর্তে সব ফ্রি মডেল রেট-লিমিটে — একটু পরে আবার চেষ্টা করুন।
                </div>
                {data?.reason && (
                  <div className="mt-2 font-mono text-[10px] text-dim">{data.reason}</div>
                )}
              </div>
            )}

            {/* Dropped seats */}
            {dropped.length > 0 && (
              <div className="mt-3.5 border-t border-hair/50 pt-3">
                <span className="micro-label">dropped · {dropped.length}</span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {dropped.map((d) => (
                    <span
                      key={d.mandate}
                      className="rounded-md border border-hair px-2 py-1 font-mono text-[9.5px] text-dim"
                      title={d.reason}
                    >
                      {MANDATE_META[d.mandate].label}
                      <span className="ml-1.5 text-bear/70">
                        {/429|rate/i.test(d.reason) ? "rate-limited" : "dropped"}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {data && (
              <div className="mt-4 border-t border-hair/50 pt-2.5 font-mono text-[9px] tracking-[0.08em] text-dim">
                brief {dhakaTime(data.brief_generated_at)} · run {dhakaTime(data.generated_at)} · advisory only
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
