"use client";

/** Glossary term — a dotted-underline trigger that reveals a bilingual tooltip
 *  (English name · Bengali name · Bengali explanation) on hover (desktop) or
 *  tap/focus (touch).
 *
 *  The tooltip is rendered in a <body> portal at position:fixed and positioned
 *  from the trigger's live rect, then clamped inside the viewport. That is the
 *  root-cause fix for the earlier clipping: an absolutely-positioned tooltip was
 *  being cut off by the desk rail's `overflow-y-auto` and by transformed
 *  ancestors. A fixed portal escapes both. Reveal is opacity-only (C5 contract).
 */

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { GLOSSARY, type GlossaryKey } from "@/lib/glossary";

const TIP_W = 300; // matches .term-tip-fx width
const GAP = 9; // px between trigger and tooltip
const MARGIN = 8; // min gap to the viewport edge

type Pos = { top: number; left: number; place: "above" | "below" };

export default function Term({
  k,
  children,
  className = "",
  bare = false,
}: {
  k: GlossaryKey;
  children: React.ReactNode;
  className?: string;
  /** drop the dotted underline (for badges/chips that carry their own styling) */
  bare?: boolean;
  /** legacy placement hints — positioning is now automatic + viewport-clamped */
  below?: boolean;
  edge?: boolean;
}) {
  const g = GLOSSARY[k];
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<Pos | null>(null);

  // Horizontal placement + a "below" first guess (needs no tooltip height).
  const measure = useCallback((): Pos | null => {
    const el = triggerRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    let left = r.left + r.width / 2 - TIP_W / 2;
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - TIP_W - MARGIN));
    return { top: r.bottom + GAP, left, place: "below" };
  }, []);

  const show = useCallback(() => setPos(measure()), [measure]);
  const hide = useCallback(() => setPos(null), []);

  // Correct vertical placement against the tooltip's real height — runs before
  // paint, so the first guess is never visible (no flicker). Converges in one
  // pass: once top/place match, no further setState.
  useLayoutEffect(() => {
    if (!pos || !tipRef.current || !triggerRef.current) return;
    const h = tipRef.current.offsetHeight;
    const r = triggerRef.current.getBoundingClientRect();
    const vh = window.innerHeight;
    const belowTop = r.bottom + GAP;
    const aboveTop = r.top - GAP - h;
    let place: Pos["place"] = "below";
    let top = belowTop;
    if (belowTop + h > vh - MARGIN && aboveTop >= MARGIN) {
      place = "above";
      top = aboveTop;
    }
    top = Math.max(MARGIN, Math.min(top, vh - h - MARGIN));
    if (top !== pos.top || place !== pos.place) {
      setPos({ top, left: pos.left, place });
    }
  }, [pos]);

  // Keep the tooltip pinned to the trigger while open (rail scroll / resize).
  // rAF-throttled: native scroll events can fire dozens of times/sec, and each
  // one forces a layout read (getBoundingClientRect) + a React state update —
  // coalescing to one per frame keeps a scroll gesture smooth even with a
  // tooltip open, without changing how closely the tooltip tracks its trigger.
  useLayoutEffect(() => {
    if (!pos) return;
    let raf = 0;
    const onMove = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        setPos(measure());
      });
    };
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
      if (raf) cancelAnimationFrame(raf);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pos === null, measure]);

  return (
    <span
      ref={triggerRef}
      className={`${bare ? "term-bare" : "term"} ${className}`}
      tabIndex={0}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {pos &&
        typeof document !== "undefined" &&
        createPortal(
          <span
            ref={tipRef}
            role="tooltip"
            className="term-tip-fx"
            style={{ top: pos.top, left: pos.left }}
          >
            <span className="term-tip-en">{g.en}</span>
            <span className="term-tip-bn">{g.bn}</span>
            <span className="term-tip-desc">{g.desc}</span>
          </span>,
          document.body,
        )}
    </span>
  );
}
