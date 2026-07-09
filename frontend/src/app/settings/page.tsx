"use client";

/** Settings — desk mode, risk, spend caps, model roster, data providers.
 *  The desk-mode toggle is REAL (P3 · FR-5): it reads/writes
 *  `/monitor/mode` on the backend, which the background scanner checks on
 *  every tick — flip it here and the very next scheduled scan honors it, no
 *  restart needed. The rest of this page stays a design shell: real values
 *  live server-side in YAML/env (CLAUDE.md invariant 6 — config over code).
 */

import { useEffect, useState } from "react";

import SiteHeader from "@/components/SiteHeader";
import { fetchScannerMode, setScannerMode, type ScannerMode } from "@/lib/api";

const RISK_PRESETS = ["0.5", "1.0", "1.5", "2.0"] as const;

const ROSTER = [
  { seat: "TREND", model: "deepseek-v3 · openrouter", gold: false },
  { seat: "CONTRARIAN", model: "llama-3.3-70b · groq", gold: false },
  { seat: "DERIVATIVES", model: "qwen2.5-72b · openrouter", gold: false },
  { seat: "RISK OFFICER", model: "gemini-2.0-flash · google", gold: false },
  { seat: "CIO · SYNTHESIS", model: "claude · interactive via MCP", gold: true },
];

const PROVIDERS: Array<{ name: string; scope: string; state: "live" | "key needed" }> = [
  { name: "binance spot + futures", scope: "ohlcv · funding · oi · l/s", state: "live" },
  { name: "alternative.me", scope: "fear & greed", state: "live" },
  { name: "fred", scope: "macro series", state: "key needed" },
  { name: "finnhub", scope: "economic calendar", state: "key needed" },
  { name: "openrouter / groq / google", scope: "analyst models", state: "key needed" },
];

function SectionCard({
  title,
  delay,
  children,
  gold = false,
}: {
  title: string;
  delay: number;
  children: React.ReactNode;
  gold?: boolean;
}) {
  return (
    <div className={`card dp-rise ${gold ? "card-ai" : ""}`} style={{ animationDelay: `${delay}ms` }}>
      <div
        className={`border-b px-5 py-3 ${gold ? "border-[rgba(232,197,116,0.18)]" : "border-hair/70"}`}
      >
        <span className="micro-label" style={gold ? { color: "var(--ai-gold)", opacity: 0.9 } : undefined}>
          {title}
        </span>
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const [mode, setMode] = useState<ScannerMode>("manual");
  const [modeReady, setModeReady] = useState(false);
  const [risk, setRisk] = useState<(typeof RISK_PRESETS)[number]>("1.0");
  const active = mode === "active";

  useEffect(() => {
    fetchScannerMode()
      .then((r) => setMode(r.mode))
      .catch(() => {})
      .finally(() => setModeReady(true));
  }, []);

  const chooseMode = (m: ScannerMode) => {
    if (m === mode) return;
    const prev = mode;
    setMode(m); // optimistic — the toggle should feel instant
    setScannerMode(m).catch(() => setMode(prev)); // backend unreachable → revert
  };

  return (
    <main className="flex min-h-screen flex-col">
      <SiteHeader />

      <div className="mx-auto w-full max-w-[980px] flex-1 px-4 py-6 sm:px-6">
        <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-[28px] font-bold tracking-tight text-hi">
            Desk <span className="text-gold">settings</span>
            <span className="bn-sub ml-3">ডেস্ক সেটিংস</span>
          </h1>
        </div>

        <div className="grid gap-4 pb-8 lg:grid-cols-2">
          {/* Mode — REAL: writes /monitor/mode, read by the background scanner */}
          <SectionCard title="desk mode · fr-5" delay={0}>
            <div className={`relative flex rounded-lg border border-hair bg-abyss/60 p-0.5 ${modeReady ? "" : "opacity-60"}`}>
              <span
                className="absolute top-0.5 bottom-0.5 left-0.5 rounded-md bg-raised"
                style={{
                  width: "calc((100% - 4px) / 2)",
                  transform: `translateX(${active ? 100 : 0}%)`,
                  transition: "transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1)",
                }}
              />
              {(["manual", "active"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => chooseMode(m)}
                  disabled={!modeReady}
                  className={`relative z-10 flex-1 py-2 text-center font-mono text-xs uppercase tracking-[0.14em] transition-colors duration-200 ${
                    (m === "active") === active ? "text-hi" : "text-dim hover:text-mid"
                  }`}
                >
                  {m === "active" && (
                    <span className={`live-dot mr-2 ${active ? "bg-warn" : "bg-raised"}`} />
                  )}
                  {m}
                </button>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-snug text-dim">
              <span className="text-mid">Manual</span> — the desk analyzes only when you ask.{" "}
              <span className="text-mid">Active</span> — the backend scans your watchlist on
              an interval and logs notable conditions. Alerts never execute anything; advisory
              only (ADR-0008).
            </p>
            <p className="font-bn mt-1.5 text-[11px] leading-relaxed text-dim">
              ম্যানুয়াল — শুধু চাইলে বিশ্লেষণ। অ্যাক্টিভ — ব্যাকগ্রাউন্ডে নিয়মিত স্ক্যান করে
              নজরদারি করে, নিজে থেকে কিছু কার্যকর করে না।
            </p>
          </SectionCard>

          {/* Risk */}
          <SectionCard title="risk per trade" delay={60}>
            <div className="flex flex-wrap items-center gap-2">
              {RISK_PRESETS.map((r) => (
                <button
                  key={r}
                  onClick={() => setRisk(r)}
                  className={`rounded-md border px-3.5 py-1.5 font-mono text-[13px] tabular-nums transition-colors duration-150 ${
                    risk === r
                      ? "border-pulse/40 bg-raised text-hi"
                      : "border-hair text-dim hover:text-mid"
                  }`}
                >
                  {r}%
                </button>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-snug text-dim">
              Position size is derived: risk % of account ÷ distance to stop. The desk
              publishes size as a %, never a leverage dare.
            </p>
          </SectionCard>

          {/* Spend */}
          <SectionCard title="llm spend · nfr-4" delay={120}>
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[22px] font-light tabular-nums text-hi">$0.00</span>
              <span className="font-mono text-[11px] tabular-nums text-dim">cap $10.00 / mo</span>
            </div>
            <div className="mt-2.5 h-[3px] overflow-hidden rounded-full bg-raised">
              <div className="h-full w-[2%] rounded-full bg-bull opacity-80" />
            </div>
            <p className="mt-3 text-[11px] leading-snug text-dim">
              Hard cap enforced server-side; Full Desk runs refuse to start past it. The
              interactive CIO rides your Claude subscription — $0 metered.
            </p>
          </SectionCard>

          {/* Roster */}
          <SectionCard title="model roster · models.yaml" delay={180} gold>
            <div className="space-y-2.5">
              {ROSTER.map((r) => (
                <div key={r.seat} className="flex items-center text-[11.5px]">
                  <span className="w-[118px] shrink-0 font-mono text-[10px] tracking-[0.1em] text-mid">
                    {r.seat}
                  </span>
                  <span className="leader" />
                  <span className={`font-mono ${r.gold ? "text-gold" : "text-hi"}`}>{r.model}</span>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-snug text-dim">
              Any seat swaps to any LiteLLM-routable model — one YAML line, zero code
              (ADR-0004). Gold seat = the desk&apos;s judgment voice.
            </p>
          </SectionCard>

          {/* Providers */}
          <SectionCard title="data providers · providers.yaml" delay={240}>
            <div className="space-y-2.5">
              {PROVIDERS.map((p) => (
                <div key={p.name} className="flex items-center text-[11.5px]">
                  <span
                    className={`live-dot mr-2.5 ${p.state === "live" ? "bg-bull" : "bg-raised"}`}
                  />
                  <span className="font-mono text-hi">{p.name}</span>
                  <span className="leader" />
                  <span className={`font-mono text-[10px] ${p.state === "live" ? "text-bull" : "text-warn"}`}>
                    {p.state}
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-snug text-dim">
              New source = one adapter class + one YAML entry (ADR-0003). Keys live
              server-side in env — never in this browser.
            </p>
          </SectionCard>

          {/* Config-over-code note */}
          <SectionCard title="where settings actually live" delay={300}>
            <p className="text-[11.5px] leading-relaxed text-mid">
              This screen is a design shell. Real values persist in{" "}
              <span className="font-mono text-hi">config/*.yaml</span> and env on the
              server (CLAUDE.md invariant 6: config over code) — the UI becomes a thin
              editor over them in P2/P3, so nothing here can drift from what the engine
              actually runs.
            </p>
          </SectionCard>
        </div>
      </div>
    </main>
  );
}
