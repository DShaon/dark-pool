"use client";

/** Source badge (ADR-0017 §5) — a small ⓘ on every data-bearing surface. Hover
 *  or focus reveals where that data came from: an external vendor, our
 *  deterministic engine, or an AI model (with the actual model id). Same
 *  fixed-portal, viewport-clamped tooltip mechanism as `Term` (escapes rail
 *  overflow + transformed ancestors). Reveal is opacity-only (C5).
 *
 *  The colour of the ⓘ encodes the kind at a glance: dim (vendor), teal
 *  (engine/deterministic), gold (AI judgment) — consistent with the desk's
 *  "fact vs. opinion" rule.
 */

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { PROVENANCE, kindLabel, type ProvKind } from "@/lib/provenance";

const TIP_W = 300;
const GAP = 9;
const MARGIN = 8;

const KIND_COLOR: Record<ProvKind, string> = {
  vendor: "var(--text-dim)",
  engine: "var(--bull)",
  ai: "var(--ai-gold)",
};

type Pos = { top: number; left: number };

export default function SourceBadge({
  surface,
  detail,
  className = "",
}: {
  surface: string;
  /** runtime addendum, e.g. the actual AI model id / synthesizer */
  detail?: string | null;
  className?: string;
}) {
  const prov = PROVENANCE[surface];
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<Pos | null>(null);

  const measure = useCallback((): Pos | null => {
    const el = triggerRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    let left = r.left + r.width / 2 - TIP_W / 2;
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - TIP_W - MARGIN));
    return { top: r.bottom + GAP, left };
  }, []);

  const show = useCallback(() => setPos(measure()), [measure]);
  const hide = useCallback(() => setPos(null), []);

  useLayoutEffect(() => {
    if (!pos || !tipRef.current || !triggerRef.current) return;
    const h = tipRef.current.offsetHeight;
    const r = triggerRef.current.getBoundingClientRect();
    const vh = window.innerHeight;
    let top = r.bottom + GAP;
    if (top + h > vh - MARGIN && r.top - GAP - h >= MARGIN) top = r.top - GAP - h;
    top = Math.max(MARGIN, Math.min(top, vh - h - MARGIN));
    if (top !== pos.top) setPos({ top, left: pos.left });
  }, [pos]);

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
  }, [pos === null, measure]);

  if (!prov) return null;
  const kl = kindLabel(prov.kind);

  return (
    <span
      ref={triggerRef}
      className={`source-badge ${className}`}
      style={{ color: KIND_COLOR[prov.kind] }}
      tabIndex={0}
      role="button"
      aria-label={`data source: ${kl.en}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      ⓘ
      {pos &&
        typeof document !== "undefined" &&
        createPortal(
          <span ref={tipRef} role="tooltip" className="term-tip-fx" style={{ top: pos.top, left: pos.left }}>
            <span className="term-tip-en" style={{ color: KIND_COLOR[prov.kind] }}>
              {kl.en}
            </span>
            <span className="term-tip-bn">{kl.bn}</span>
            <span className="term-tip-desc">{prov.en}</span>
            <span className="term-tip-desc font-bn" style={{ marginTop: 4 }}>
              {prov.bn}
            </span>
            {detail && (
              <span className="term-tip-desc" style={{ marginTop: 4, opacity: 0.8 }}>
                model: {detail}
              </span>
            )}
          </span>,
          document.body,
        )}
    </span>
  );
}
