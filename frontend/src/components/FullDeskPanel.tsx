"use client";

/** Full Desk overlay (P2) — the mandate-analyst panel in a focused view.
 *  Shows each surviving analyst's evidence-locked read (bilingual), the raw
 *  direction tally, and the seats that dropped and why. Graceful when the free
 *  providers are rate-limited: it explains the degradation instead of breaking.
 *
 *  The single CIO verdict (synthesis + calibrated confidence + sizing) is a
 *  separate Fable-tier step — shown here as an explicit "pending" placeholder,
 *  never faked.
 */

import { useEffect } from "react";

import Term from "@/components/Term";
import { formatPrice, type AnalystThesis, type DeskPanelResponse, type Mandate } from "@/lib/api";
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
  no_trade: { word: "NO TRADE", arrow: "◆" },
};

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
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

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
              <div className="text-[18px] font-bold tracking-tight text-gold">
                Full Desk <span className="text-hi">· {symbol}</span>
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
            {/* Tally + CIO placeholder */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="micro-label">reads</span>
              {(["long", "short", "no_trade"] as const).map((d) => (
                <span
                  key={d}
                  className="rounded-md border border-hair px-2 py-px font-mono text-[10.5px] tabular-nums text-mid"
                >
                  {DIR[d].word} <span className="text-gold">{tally[d] ?? 0}</span>
                </span>
              ))}
              <span className="ml-auto rounded-md border border-[rgba(232,197,116,0.3)] px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-gold/80">
                CIO verdict · pending <span className="text-dim">(Fable)</span>
              </span>
            </div>
            <p className="mt-1.5 text-[10.5px] leading-snug text-dim">
              The panel argues; the CIO decides. The single synthesized plan + calibrated
              confidence + position size land with the Fable pass — analysts here never fake it.
            </p>

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
