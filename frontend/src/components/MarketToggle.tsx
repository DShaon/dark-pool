"use client";

/** Asset-class switch (P4) — CRYPTO ⇄ FOREX. A two-segment pill with a sliding
 *  highlight (the same motion vocabulary as the timeframe tabs and the desk-mode
 *  toggle), so switching the whole desk's asset class feels like a dark/light
 *  flip. Crypto glows cyan (live-data), forex amber — a quiet cue for which
 *  world you're in. transform/opacity only (C5 contract). */

export type AssetClass = "crypto" | "forex";

const SEGMENTS: Array<{ key: AssetClass; label: string; glyph: string; tint: string }> = [
  { key: "crypto", label: "crypto", glyph: "₿", tint: "text-pulse" },
  { key: "forex", label: "forex", glyph: "€", tint: "text-warn" },
];

export default function MarketToggle({
  value,
  onChange,
}: {
  value: AssetClass;
  onChange: (v: AssetClass) => void;
}) {
  const idx = value === "crypto" ? 0 : 1;
  return (
    <div
      className="relative flex rounded-lg border border-hair bg-abyss/60 p-0.5"
      role="tablist"
      aria-label="asset class"
    >
      <span
        className="absolute top-0.5 bottom-0.5 left-0.5 rounded-md bg-raised"
        style={{
          width: "calc((100% - 4px) / 2)",
          transform: `translateX(${idx * 100}%)`,
          transition: "transform 260ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        }}
      />
      {SEGMENTS.map((s) => {
        const on = s.key === value;
        return (
          <button
            key={s.key}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(s.key)}
            className={`relative z-10 flex items-center gap-1.5 px-3 py-1 font-mono text-[10.5px] uppercase tracking-[0.14em] transition-colors duration-200 ${
              on ? "text-hi" : "text-dim hover:text-mid"
            }`}
          >
            <span className={on ? s.tint : "text-dim"}>{s.glyph}</span>
            {s.label}
          </button>
        );
      })}
    </div>
  );
}
