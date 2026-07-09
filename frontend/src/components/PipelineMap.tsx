"use client";

/** Desk Pipeline Map (ADR-0011) / Consensus Constellation (C4 signature #2).
 *  Four mandate seats as nodes on a diamond. Nodes that share the plurality
 *  read glow gold (in the cluster); dissenters dim; dropped seats are hollow.
 *  Edges are solid gold between analysts that AGREE, dashed-dim otherwise. The
 *  glyph breathes ±1.5% over 4s (static under reduced-motion).
 *
 *  With a real Full Desk run (`panel`), agreement is computed from the theses.
 *  Without one it shows a SAMPLE constellation. The centre prints the plurality
 *  direction + count — a raw tally, NOT a consensus verdict: the CIO's single
 *  synthesized call + calibrated confidence are a separate Fable-tier step.
 */

import { memo } from "react";

import SampleTag from "@/components/SampleTag";
import Term from "@/components/Term";
import type { DeskPanelResponse } from "@/lib/api";

const W = 320;
const H = 178;
const CX = W / 2;
const CY = H / 2;

type NodePos = { key: string; label: string; x: number; y: number };

const NODES: NodePos[] = [
  { key: "trend", label: "TREND", x: CX, y: 26 },
  { key: "derivatives", label: "DERIV", x: W - 52, y: CY },
  { key: "risk", label: "RISK", x: CX, y: H - 26 },
  { key: "contrarian", label: "CNTRN", x: 52, y: CY },
];

const EDGES: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 0], [0, 2], [1, 3],
];

// Sample agreement (no live run): trend/deriv/risk cluster, contrarian dissents.
const SAMPLE_AGREE: Record<string, boolean> = {
  trend: true,
  derivatives: true,
  risk: true,
  contrarian: false,
};

const DIR_LABEL: Record<string, string> = {
  long: "LONG",
  short: "SHORT",
  no_trade: "NO-TRADE",
};

// Home() re-renders every 15s/30s poll; `panel` only changes on a Full Desk
// run and `onOpenDesk` is a stable useCallback, so memo skips needless SVG
// reconciliation of the constellation on unrelated parent ticks.
function PipelineMap({
  panel,
  onOpenDesk,
}: {
  panel?: DeskPanelResponse | null;
  onOpenDesk?: () => void;
}) {
  const real = !!panel && panel.theses.length > 0;

  const dirBy: Record<string, string> = {};
  if (real) for (const t of panel!.theses) dirBy[t.mandate] = t.read.direction;

  const ranked = real
    ? Object.entries(panel!.tally)
        .filter(([, c]) => c > 0)
        .sort((a, b) => b[1] - a[1])
    : [];
  const plurality = ranked.length ? ranked[0][0] : null;
  const pluralityCount = ranked.length ? ranked[0][1] : 0;

  const nodeAgrees = (key: string): { present: boolean; agrees: boolean } => {
    if (!real) return { present: true, agrees: SAMPLE_AGREE[key] };
    const present = key in dirBy;
    return { present, agrees: present && dirBy[key] === plurality };
  };

  const edgeAgrees = (a: number, b: number): boolean => {
    if (!real) return SAMPLE_AGREE[NODES[a].key] && SAMPLE_AGREE[NODES[b].key];
    const da = dirBy[NODES[a].key];
    const db = dirBy[NODES[b].key];
    return !!da && da === db;
  };

  const centreText = real ? (plurality ? DIR_LABEL[plurality] ?? plurality : "—") : "ALIGNED";

  return (
    <div className="card dp-rise" style={{ animationDelay: "60ms" }}>
      <div className="flex items-start justify-between gap-3 border-b border-hair/70 px-5 py-2.5">
        <span className="min-w-0">
          <Term k="CONSENSUS" className="micro-label block">desk pipeline · consensus</Term>
          <span className="bn-sub mt-0.5">বিশ্লেষকদের ঐকমত্য</span>
        </span>
        <div className="flex shrink-0 items-center gap-2">
          {real ? (
            <span
              className="rounded-md border px-1.5 py-px font-mono text-[9px] tracking-[0.12em]"
              style={{
                borderColor: panel!.status === "ok" ? "rgba(232,197,116,0.4)" : "var(--line-hair)",
                color: panel!.status === "ok" ? "var(--ai-gold)" : "var(--text-dim)",
              }}
            >
              {panel!.theses.length}/{panel!.theses.length + panel!.dropped.length} LIVE
            </span>
          ) : (
            <SampleTag />
          )}
          {onOpenDesk && (
            <button
              onClick={onOpenDesk}
              className="rounded-md border border-[rgba(232,197,116,0.35)] px-2 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-gold/90 transition-colors duration-200 hover:bg-[rgba(232,197,116,0.08)]"
              title="run the full analyst desk"
            >
              Full Desk →
            </button>
          )}
        </div>
      </div>
      <div className="flex justify-center px-3 py-2">
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          aria-label={real ? `Consensus: ${centreText} ${pluralityCount} of ${panel!.theses.length}` : "Consensus map (sample)"}
        >
          <g className="dp-breathe">
            {EDGES.map(([a, b]) => {
              const agree = edgeAgrees(a, b);
              return (
                <line
                  key={`${a}-${b}`}
                  x1={NODES[a].x} y1={NODES[a].y} x2={NODES[b].x} y2={NODES[b].y}
                  stroke={agree ? "var(--ai-gold)" : "var(--text-dim)"}
                  strokeWidth={agree ? 1.2 : 0.8}
                  strokeDasharray={agree ? undefined : "3 5"}
                  opacity={agree ? 0.55 : 0.28}
                />
              );
            })}

            <text
              x={CX} y={real ? CY : CY + 3} textAnchor="middle"
              fill="var(--ai-gold)" fontSize="10" letterSpacing="0.16em"
              fontFamily="var(--font-geist-mono), monospace"
            >
              {centreText}
            </text>
            {real && plurality && (
              <text
                x={CX} y={CY + 13} textAnchor="middle"
                fill="var(--text-dim)" fontSize="8" letterSpacing="0.1em"
                fontFamily="var(--font-geist-mono), monospace"
              >
                {pluralityCount}/{panel!.theses.length}
              </text>
            )}

            {NODES.map((n) => {
              const { present, agrees } = nodeAgrees(n.key);
              const ringColor = !present
                ? "var(--line-hair)"
                : agrees
                  ? "var(--ai-gold)"
                  : "var(--line-hair)";
              return (
                <g key={n.key} opacity={present ? 1 : 0.4}>
                  <circle
                    cx={n.x} cy={n.y} r="11"
                    fill="var(--bg-raised)"
                    stroke={ringColor}
                    strokeWidth="1.2"
                    strokeDasharray={present ? undefined : "2 3"}
                    opacity={present ? (agrees ? 0.95 : 0.7) : 0.6}
                  />
                  <circle
                    cx={n.x} cy={n.y} r="2.5"
                    fill={present && agrees ? "var(--ai-gold)" : "var(--text-dim)"}
                  />
                  <text
                    x={n.x}
                    y={n.y < CY ? n.y - 17 : n.y > CY ? n.y + 25 : n.y - 17}
                    textAnchor="middle"
                    fill={present && agrees ? "var(--text-mid)" : "var(--text-dim)"}
                    fontSize="8.5" letterSpacing="0.14em"
                    fontFamily="var(--font-geist-mono), monospace"
                  >
                    {n.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}

export default memo(PipelineMap);
