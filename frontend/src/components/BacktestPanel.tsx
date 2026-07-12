"use client";

/** Backtest panel (P5 · ADR-0020) — walk-forward replay of the setup variants
 *  over real Binance history, run server-side as a background job. ENGINE
 *  surface (teal/red semantics, never gold — no AI anywhere in this loop).
 *  The assumptions block ships with every report and renders here: a
 *  simulation's numbers are only as honest as its stated rules (NFR-7).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import SourceBadge from "@/components/SourceBadge";
import {
  fetchBacktestReport,
  fetchBacktestStatus,
  startBacktest,
  type BacktestJobStatus,
  type BacktestReport,
  type BacktestVariantResult,
} from "@/lib/api";

const WINDOWS = [30, 60, 90] as const;
const POLL_MS = 2000;

const VARIANT_LABEL: Record<string, string> = {
  scalp: "PERP 5x scalp",
  intraday: "PERP 3x intraday",
  swing: "MARGIN 2x swing",
  spot: "SPOT accumulate",
};

function fmtR(v: number | null | undefined, signed = true): string {
  if (v == null) return "—";
  const s = v.toFixed(2);
  return signed && v > 0 ? `+${s}` : s;
}

function rTone(v: number | null | undefined): string {
  if (v == null) return "text-dim";
  return v > 0 ? "text-bull" : v < 0 ? "text-bear" : "text-mid";
}

function Equity({ points }: { points: number[] }) {
  if (points.length < 2) return <span className="text-[10px] text-dim">—</span>;
  const w = 96;
  const h = 26;
  const all = [0, ...points];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const step = w / (all.length - 1);
  const pts = all
    .map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / span) * (h - 2) - 1).toFixed(1)}`)
    .join(" ");
  const up = points[points.length - 1] > 0;
  return (
    <svg width={w} height={h} className="block" aria-hidden>
      <polyline
        points={pts}
        fill="none"
        stroke={up ? "var(--bull)" : "var(--bear)"}
        strokeWidth="1.2"
        opacity="0.9"
      />
    </svg>
  );
}

function McCell({ v }: { v: BacktestVariantResult }) {
  if (!v.monte_carlo) {
    return (
      <span className="text-[10px] leading-tight text-dim" title={v.mc_note ?? undefined}>
        {v.n_trades > 0 ? `needs ${Math.max(0, 10 - v.n_trades)} more` : "—"}
      </span>
    );
  }
  const mc = v.monte_carlo;
  const risky = mc.prob_loss >= 0.3;
  return (
    <span className="font-mono text-[10.5px] tabular-nums">
      <span className="text-mid">
        {fmtR(mc.total_r_p5)}…{fmtR(mc.total_r_p95)}R
      </span>{" "}
      <span className={risky ? "text-warn" : "text-bull"}>
        · P(loss) {(mc.prob_loss * 100).toFixed(0)}%
      </span>
    </span>
  );
}

export default function BacktestPanel() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [days, setDays] = useState<number>(30);
  const [job, setJob] = useState<BacktestJobStatus | null>(null);
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAssumptions, setShowAssumptions] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const loadReport = useCallback(async (sym: string) => {
    try {
      setReport(await fetchBacktestReport(sym));
    } catch {
      /* no stored report yet — fine */
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const s = await fetchBacktestStatus();
      setJob(s);
      if (s.state !== "running") {
        stopPoll();
        if (s.state === "done" && s.symbol) {
          setSymbol(s.symbol);
          await loadReport(s.symbol);
        }
        if (s.state === "error") setError(s.message ?? "backtest failed");
      }
    } catch {
      /* backend briefly away — keep polling */
    }
  }, [loadReport, stopPoll]);

  useEffect(() => {
    // Adopt whatever the server is doing (a run survives a page reload).
    void (async () => {
      try {
        const s = await fetchBacktestStatus();
        setJob(s);
        if (s.state === "running") {
          timer.current = setInterval(() => void poll(), POLL_MS);
        } else if (s.state === "done" && s.symbol) {
          setSymbol(s.symbol);
          await loadReport(s.symbol);
        } else {
          await loadReport("BTCUSDT");
        }
      } catch {
        /* backend away */
      }
    })();
    return stopPoll;
  }, [poll, loadReport, stopPoll]);

  async function run() {
    setError(null);
    let sym = symbol.trim().toUpperCase();
    if (!sym) return;
    if (!/USD[TC]$/.test(sym) && /^[A-Z0-9]{2,10}$/.test(sym)) sym += "USDT";
    setSymbol(sym);
    try {
      await startBacktest(sym, days);
      setJob({ state: "running", symbol: sym, days, progress: 0, message: "starting" });
      stopPoll();
      timer.current = setInterval(() => void poll(), POLL_MS);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not start the backtest");
    }
  }

  const running = job?.state === "running";

  return (
    <div className="card dp-rise mt-4" style={{ animationDelay: "285ms" }}>
      <div className="flex items-start justify-between gap-3 border-b border-hair/70 px-5 py-3">
        <span className="min-w-0">
          <span className="micro-label block">
            backtest · same rules, real history <SourceBadge surface="backtest" />
          </span>
          <span className="bn-sub mt-0.5">ব্যাকটেস্ট — একই নিয়ম, বাস্তব ইতিহাসে যাচাই</span>
        </span>
        {report && !running && (
          <span className="shrink-0 rounded-md border border-hair px-2 py-px font-mono text-[9px] tracking-[0.12em] text-bull">
            {report.symbol} · {report.requested_days}d · {report.n_decisions} decisions
          </span>
        )}
      </div>

      {/* controls */}
      <div className="flex flex-wrap items-center gap-2 px-5 pt-3">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && !running && void run()}
          placeholder="BTCUSDT"
          disabled={running}
          className="w-[120px] rounded-md border border-hair bg-raised/60 px-2 py-1.5 font-mono text-[11px] tracking-[0.06em] text-hi outline-none focus:border-pulse/50 disabled:opacity-50"
        />
        <div className="flex overflow-hidden rounded-md border border-hair">
          {WINDOWS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              disabled={running}
              className={`px-2.5 py-1.5 font-mono text-[10px] tabular-nums transition-colors disabled:opacity-50 ${
                days === d ? "bg-raised text-hi" : "text-dim hover:text-mid"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
        <button
          onClick={() => void run()}
          disabled={running}
          className="rounded-md border border-pulse/40 px-3 py-1.5 font-mono text-[10px] tracking-[0.1em] text-pulse transition-colors hover:bg-raised disabled:opacity-50"
        >
          {running ? "RUNNING…" : "▶ RUN"}
        </button>
        {running && job && (
          <span className="flex min-w-[160px] flex-1 items-center gap-2">
            <span className="h-[3px] flex-1 overflow-hidden rounded-full bg-raised">
              <span
                className="block h-full rounded-full bg-pulse/70 transition-[width] duration-500"
                style={{ width: `${Math.round(job.progress * 100)}%` }}
              />
            </span>
            <span className="shrink-0 font-mono text-[9.5px] text-dim">
              {job.message} · {Math.round(job.progress * 100)}%
            </span>
          </span>
        )}
        {error && <span className="text-[10.5px] text-bear">{error}</span>}
      </div>

      {/* results */}
      {report ? (
        <div className="overflow-x-auto px-5 pb-2 pt-3">
          <table className="w-full min-w-[720px] text-left">
            <thead>
              <tr className="border-b border-hair/60 font-mono text-[9px] uppercase tracking-[0.14em] text-dim">
                <th className="py-2 pr-3">style</th>
                <th className="py-2 pr-3">trades</th>
                <th className="py-2 pr-3">win%</th>
                <th className="py-2 pr-3">avg R</th>
                <th className="py-2 pr-3">total R</th>
                <th className="py-2 pr-3">max DD</th>
                <th className="py-2 pr-3">equity</th>
                <th className="py-2">monte carlo (p5…p95)</th>
              </tr>
            </thead>
            <tbody>
              {report.variants.map((v) => (
                <tr key={v.key} className="border-b border-hair/40 last:border-0">
                  <td className="py-2.5 pr-3">
                    <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-hi">
                      {VARIANT_LABEL[v.key] ?? v.key}
                    </span>
                    {v.n_open_excluded > 0 && (
                      <span className="ml-1.5 text-[9px] text-dim">+{v.n_open_excluded} open</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-3 font-mono text-[11px] tabular-nums text-mid">
                    {v.n_trades > 0 ? `${v.n_wins}W ${v.n_losses}L` : "0"}
                  </td>
                  <td className="py-2.5 pr-3 font-mono text-[11px] tabular-nums text-mid">
                    {v.win_rate != null ? `${Math.round(v.win_rate * 100)}%` : "—"}
                  </td>
                  <td className={`py-2.5 pr-3 font-mono text-[11px] tabular-nums ${rTone(v.avg_r)}`}>
                    {fmtR(v.avg_r)}
                  </td>
                  <td className={`py-2.5 pr-3 font-mono text-[11px] tabular-nums ${rTone(v.n_trades ? v.total_r : null)}`}>
                    {v.n_trades ? fmtR(v.total_r) : "—"}
                  </td>
                  <td className="py-2.5 pr-3 font-mono text-[11px] tabular-nums text-mid">
                    {v.n_trades ? `−${v.max_drawdown_r.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-2.5 pr-3"><Equity points={v.equity_r} /></td>
                  <td className="py-2.5"><McCell v={v} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        !running && (
          <p className="px-5 py-4 text-[11.5px] text-dim">
            no backtest stored yet — pick a symbol and window, then RUN. the engine replays
            the exact setup rules over past candles (fees charged, no lookahead).
            <span className="bn-sub mt-1 block">
              এখনও কোনো ব্যাকটেস্ট নেই — সিম্বল আর সময় বেছে RUN চাপুন।
            </span>
          </p>
        )
      )}

      {/* assumptions — every number traces to a stated rule */}
      {report && (
        <div className="border-t border-hair/50 px-5 py-2.5">
          <button
            onClick={() => setShowAssumptions((s) => !s)}
            className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-dim transition-colors hover:text-mid"
          >
            {showAssumptions ? "▾" : "▸"} assumptions · অনুমানগুলো
          </button>
          {showAssumptions && (
            <ul className="mt-2 space-y-1 pb-1 text-[10.5px] leading-snug text-dim">
              <li>▸ {report.assumptions.fill_model}</li>
              <li>▸ {report.assumptions.fill_bar_rule}</li>
              <li>▸ {report.assumptions.both_touch_rule}</li>
              <li>▸ {report.assumptions.gap_rule}</li>
              <li>▸ {report.assumptions.funding_note}</li>
              <li>
                ▸ fees/side:{" "}
                {Object.entries(report.assumptions.fees_bps_per_side)
                  .map(([k, b]) => `${k} ${b}bps`)
                  .join(" · ")}{" "}
                + {report.assumptions.slippage_bps_per_side}bps slippage · decisions every{" "}
                {report.assumptions.decision_interval} · exits on {report.assumptions.exit_interval}
              </li>
              <li>
                ▸ monte carlo: {report.assumptions.mc_iterations} resamples · seed{" "}
                {report.assumptions.mc_seed} (reproducible) · needs ≥{" "}
                {report.assumptions.mc_min_trades} trades
              </li>
              {report.notes.map((n, i) => (
                <li key={i}>▸ {n}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
