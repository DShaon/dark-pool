"use client";

/** Fear & Greed instrument dial (ADR-0011: arc dials, amber needle).
 *  Pure SVG: graduated tick ring, gapped semantic arc segments, needle with
 *  counterweight hub. Motion is a single eased rotation — static under
 *  reduced-motion. */

const SEGMENTS = [
  { from: 0, to: 25, color: "var(--bear)" },
  { from: 25, to: 45, color: "var(--warn)" },
  { from: 45, to: 55, color: "var(--text-dim)" },
  { from: 55, to: 75, color: "var(--warn)" },
  { from: 75, to: 100, color: "var(--bull)" },
];

const CX = 100;
const CY = 96;
const R_ARC = 72;
const R_TICK_IN = 80;
const R_TICK_OUT = 86;

function polar(r: number, deg: number) {
  const rad = ((deg - 180) * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
}

function arcPath(r: number, fromDeg: number, toDeg: number) {
  const a = polar(r, fromDeg);
  const b = polar(r, toDeg);
  return `M ${a.x.toFixed(2)} ${a.y.toFixed(2)} A ${r} ${r} 0 0 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

export default function FearGreedDial({ value, label }: { value: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  const angle = clamped * 1.8; // 0..180
  const valueColor =
    clamped < 45 ? "var(--bear)" : clamped > 55 ? "var(--bull)" : "var(--text-mid)";

  return (
    <div className="flex items-center justify-between gap-5">
      <svg width="200" height="112" viewBox="0 0 200 112" aria-label={`Fear & Greed ${value}`}>
        {/* graduated tick ring */}
        {Array.from({ length: 21 }, (_, i) => {
          const deg = i * 9;
          const major = i % 5 === 0;
          const a = polar(major ? R_TICK_IN - 2 : R_TICK_IN, deg);
          const b = polar(R_TICK_OUT, deg);
          return (
            <line
              key={i}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={major ? "var(--text-dim)" : "var(--line-hair)"}
              strokeWidth={major ? 1.5 : 1}
            />
          );
        })}
        {/* semantic arc segments with machined gaps */}
        {SEGMENTS.map((s) => (
          <path
            key={s.from}
            d={arcPath(R_ARC, s.from * 1.8 + 1.6, s.to * 1.8 - 1.6)}
            stroke={s.color}
            strokeWidth="6.5"
            strokeLinecap="round"
            fill="none"
            opacity="0.85"
          />
        ))}
        {/* needle — eased rotation around the hub */}
        <g
          style={{
            transform: `rotate(${angle - 180}deg)`,
            transformOrigin: `${CX}px ${CY}px`,
            transition: "transform 900ms cubic-bezier(0.2, 0.8, 0.2, 1)",
          }}
        >
          <line
            x1={CX} y1={CY} x2={CX + 60} y2={CY}
            stroke="var(--warn)" strokeWidth="2" strokeLinecap="round"
          />
          <line
            x1={CX} y1={CY} x2={CX - 12} y2={CY}
            stroke="var(--warn)" strokeWidth="3" strokeLinecap="round" opacity="0.6"
          />
        </g>
        <circle cx={CX} cy={CY} r="6" fill="var(--bg-raised)" stroke="var(--warn)" strokeWidth="1.5" />
        <circle cx={CX} cy={CY} r="2" fill="var(--warn)" />
      </svg>
      <div className="text-right">
        <div
          className="font-mono text-5xl font-light tabular-nums leading-none"
          style={{ color: valueColor }}
        >
          {value}
        </div>
        <div className="micro-label mt-2">{label}</div>
      </div>
    </div>
  );
}
