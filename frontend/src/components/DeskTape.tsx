"use client";

/** Desk Tape (ADR-0011) — now LIVE (P3 · FR-5). Polls `/alerts/{symbol}` and
 *  shows the desk's real notable conditions (structure break, liquidity sweep,
 *  funding/OI extreme, price near a fresh zone, sentiment extreme) — bilingual,
 *  Dhaka-timestamped. Colors are semantic (structure teal/red, liquidity amber,
 *  activity cyan); the AI never appears here — the tape is engine facts only.
 *
 *  A newly-appearing warn/bear condition fires the Alert Bloom (C4 signature #8):
 *  an amber hairline traces the card once, then settles into the corner badge.
 */

import { memo, useEffect, useRef, useState } from "react";

import SourceBadge from "@/components/SourceBadge";
import Term from "@/components/Term";
import { fetchAlerts, type AlertEvent, type AlertTone } from "@/lib/api";
import { dhakaTime } from "@/lib/time";

const POLL_MS = 30_000;

const toneClass: Record<AlertTone, string> = {
  bull: "text-bull",
  bear: "text-bear",
  warn: "text-warn",
  dim: "text-dim",
  pulse: "text-pulse",
};

const keyOf = (a: AlertEvent) => `${a.kind}:${a.timeframe ?? "-"}:${a.message}`;

// Home() re-renders every 15s/30s poll; this component's own `symbol` prop
// only changes on a symbol switch, so memo skips needless reconciliation of
// its polling/bloom internals on unrelated parent ticks.
function DeskTape({ symbol }: { symbol: string }) {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [count, setCount] = useState(0);
  const [bloomId, setBloomId] = useState(0);
  const [live, setLive] = useState(false);
  const seen = useRef<Set<string>>(new Set());
  const firstLoad = useRef(true);

  useEffect(() => {
    // reset on symbol change — don't bloom for the new symbol's initial snapshot
    seen.current = new Set();
    firstLoad.current = true;
    setAlerts([]);
    setCount(0);
    let active = true;

    const load = async () => {
      try {
        const res = await fetchAlerts(symbol);
        if (!active) return;
        const fresh = res.alerts.filter(
          (a) => !seen.current.has(keyOf(a)) && (a.tone === "warn" || a.tone === "bear"),
        );
        res.alerts.forEach((a) => seen.current.add(keyOf(a)));
        setAlerts(res.alerts);
        setLive(true);
        if (!firstLoad.current && fresh.length) {
          setCount((n) => n + fresh.length);
          setBloomId((n) => n + 1);
        }
        firstLoad.current = false;
      } catch {
        /* keep the last snapshot on a transient failure */
      }
    };

    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [symbol]);

  return (
    <div className="card dp-rise relative flex min-h-0 flex-1 flex-col" style={{ animationDelay: "160ms" }}>
      {bloomId > 0 && (
        <svg key={bloomId} className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true">
          <rect
            x="0.5" y="0.5" width="calc(100% - 1px)" height="calc(100% - 1px)"
            rx="13" fill="none" stroke="var(--warn)" strokeWidth="1.2"
            pathLength={100} strokeDasharray="100" className="bloom-rect"
          />
        </svg>
      )}
      <div className="flex items-start justify-between gap-2 border-b border-hair/70 px-4 py-2.5">
        <span className="min-w-0">
          <span className="flex items-center gap-1.5">
            <Term k="DESK_TAPE" className="micro-label block">desk tape</Term>
            <SourceBadge surface="tape" />
          </span>
          <span className="bn-sub mt-0.5">ঘটনাপ্রবাহ · লাইভ</span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {count > 0 && (
            <span
              key={count}
              className="alert-badge rounded-md border border-warn/40 px-1.5 py-px font-mono text-[9px] tabular-nums text-warn"
            >
              ⚠ {count}
            </span>
          )}
          <span className={`live-dot mt-1 ${live ? "bg-bull" : "bg-raised"}`} />
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden px-4 py-2">
        {alerts.length === 0 ? (
          <div className="py-6 text-center">
            <div className="font-mono text-[11px] text-dim">{live ? "no notable conditions" : "reading…"}</div>
            {live && <div className="font-bn mt-1 text-[11px] text-dim">এখন সব শান্ত</div>}
          </div>
        ) : (
          alerts.map((a) => (
            <div key={keyOf(a)} className="tape-in border-b border-hair/30 py-[7px] last:border-0">
              <div className="flex items-baseline gap-2.5 text-[11px]">
                <span className="shrink-0 font-mono tabular-nums text-dim">{dhakaTime(a.at)}</span>
                <span className={`font-mono ${toneClass[a.tone]}`}>{a.message}</span>
              </div>
              <div className="font-bn mt-0.5 pl-[54px] text-[11px] leading-snug text-mid">{a.message_bn}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default memo(DeskTape);
