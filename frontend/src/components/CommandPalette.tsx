"use client";

/** Command palette (C4 signature #7) — Ctrl+K anywhere. The stage recedes
 *  4% and dims; the palette expands from a hairline into a field (180ms).
 *  Type any symbol → analyze. Arrow keys navigate, Enter selects, Esc
 *  dismisses. The directory below is the default board; free-typed symbols
 *  pass the same validation as the header form.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const DIRECTORY = [
  "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
  "DOGEUSDT", "LINKUSDT", "AVAXUSDT", "ADAUSDT", "TONUSDT",
];

export default function CommandPalette({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (symbol: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const q = query.trim().toUpperCase();
  const matches = useMemo(
    () => DIRECTORY.filter((s) => s.includes(q)).slice(0, 8),
    [q],
  );
  const freeTyped = q.length >= 5 && /^[A-Z0-9]{5,20}$/.test(q) && !matches.includes(q);
  const rows = useMemo(
    () => (freeTyped ? [q, ...matches] : matches),
    [freeTyped, q, matches],
  );

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      // focus after the summon animation starts
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => setCursor(0), [q]);

  const pick = useCallback(
    (s: string) => {
      onSelect(s);
      onClose();
    },
    [onSelect, onClose],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") onClose();
    else if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter" && rows[cursor]) {
      e.preventDefault();
      pick(rows[cursor]);
    }
  };

  if (!open) return null;

  return (
    <div
      className="palette-backdrop fixed inset-0 z-50 flex items-start justify-center pt-[18vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="palette-panel card w-[520px] max-w-[calc(100vw-32px)] overflow-hidden">
        <div className="flex items-center gap-3 border-b border-hair px-5 py-3.5">
          <span className="font-mono text-sm text-gold">▸</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            spellCheck={false}
            placeholder="Type a symbol — BTCUSDT, ETHUSDT…"
            aria-label="command palette"
            className="flex-1 bg-transparent font-mono text-[15px] tracking-wide text-hi outline-none placeholder:text-dim"
          />
          <span className="chip !py-0.5 text-[10px]">esc</span>
        </div>
        <div className="max-h-[320px] overflow-y-auto py-1.5">
          {rows.length === 0 && (
            <div className="px-5 py-3 text-sm text-dim">
              nothing on the board — type a full symbol to analyze it
            </div>
          )}
          {rows.map((s, i) => (
            <button
              key={s}
              onClick={() => pick(s)}
              onMouseEnter={() => setCursor(i)}
              className={`flex w-full items-center justify-between px-5 py-2.5 text-left transition-colors duration-100 ${
                i === cursor ? "bg-raised" : ""
              }`}
            >
              <span className="font-mono text-[13px] tracking-wide text-hi">
                {s.replace("USDT", "")}
                <span className="text-dim">/USDT</span>
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-dim">
                {i === cursor ? "analyze ↵" : freeTyped && i === 0 ? "free-typed" : ""}
              </span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-4 border-t border-hair/70 px-5 py-2 text-[10px] text-dim">
          <span>↑↓ navigate</span>
          <span>↵ analyze</span>
          <span className="ml-auto font-mono">darkpool desk</span>
        </div>
      </div>
    </div>
  );
}
