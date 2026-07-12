"use client";

/** Timeframe segmented control — sliding highlight (shared by the chart stage).
 *  transform/opacity only (C5 motion contract). */

export const TFS = ["5m", "15m", "1h", "4h", "1d"] as const;
export type TF = (typeof TFS)[number];

export default function SegTabs({ value, onChange }: { value: TF; onChange: (t: TF) => void }) {
  const idx = TFS.indexOf(value);
  return (
    <div className="relative flex rounded-lg border border-hair bg-abyss/60 p-0.5">
      <span
        className="absolute top-0.5 bottom-0.5 left-0.5 rounded-md bg-raised"
        style={{
          width: `calc((100% - 4px) / ${TFS.length})`,
          transform: `translateX(${idx * 100}%)`,
          transition: "transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1)",
        }}
      />
      {TFS.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`relative z-10 w-10 py-1 text-center font-mono text-[11px] transition-colors duration-200 sm:w-12 sm:text-xs ${
            t === value ? "text-hi" : "text-dim hover:text-mid"
          }`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
