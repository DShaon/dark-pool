"use client";

/** Paper desk (P5 · ADR-0021) — the approval gate's home.
 *
 *  The AI (CIO over MCP) and the UI can PROPOSE paper orders; only the two
 *  buttons in this panel can approve or reject one. That asymmetry is the
 *  design: a capability the AI does not have cannot be talked out of.
 *  Simulated balance, real Binance prices, costs charged both ways.
 *
 *  Owner request (2026-07-12): open positions render as exchange-style order
 *  tickets — live mark price, unrealized PnL (USD · % · R), and a stop↔target
 *  progress bar showing where price sits — plus an add-funds control and a
 *  manual "place at my own price" order form. A manual order still becomes a
 *  PENDING proposal you approve; it does NOT auto-fill on touch (that would
 *  bypass the gate — a separate, deliberate change). Account/market numerics
 *  stay obsidian+semantic; live data glows pulse-cyan; the gold chip marks
 *  AI-authored proposals only (AI judgment is always gold, C6a).
 */

import { useCallback, useEffect, useState } from "react";

import SourceBadge from "@/components/SourceBadge";
import {
  approveProposal,
  closePosition,
  depositFunds,
  fetchPaperAccount,
  fetchPositions,
  fetchProposals,
  placeMarketOrder,
  proposeOrder,
  rejectProposal,
  resetPaperAccount,
  formatPrice,
  type OrderBody,
  type PaperAccountView,
  type PaperPosition,
  type OrderProposal,
} from "@/lib/api";

const POLL_IDLE_MS = 30_000;
const POLL_LIVE_MS = 6_000; // faster while a position is open so PnL actually ticks
const ADD_CHIPS = ["1000", "5000", "10000", "50000"] as const;

function usd(v: string | null | undefined, signed = false): string {
  if (v == null) return "—";
  const n = Number(v);
  if (!isFinite(n)) return v;
  const s = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return signed && n > 0 ? `+${s}` : s;
}

function pnlTone(v: string | number | null | undefined): string {
  const n = Number(v);
  if (v == null || !isFinite(n) || n === 0) return "text-mid";
  return n > 0 ? "text-bull" : "text-bear";
}

function qtyStr(v: string): string {
  return Number(v).toLocaleString("en-US", { maximumFractionDigits: 6 });
}

const dhaka = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka", day: "2-digit", month: "short",
  hour: "2-digit", minute: "2-digit",
});

/** stop ↔ target rail with an entry tick and a live mark marker — the visual
 *  a real terminal shows for "how close am I to TP vs SL". Direction-agnostic:
 *  ends are labelled SL/TP explicitly, never assumed by side. */
function PositionBar({ pos }: { pos: PaperPosition }) {
  const entry = Number(pos.entry_price);
  const stop = Number(pos.stop);
  const target = Number(pos.target);
  const mark = pos.mark_price != null ? Number(pos.mark_price) : null;
  const lo = Math.min(stop, target);
  const hi = Math.max(stop, target);
  const span = hi - lo;
  if (!(span > 0)) return null;
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - lo) / span) * 100));
  const entryPct = pct(entry);
  const markPct = mark != null ? pct(mark) : null;
  const inProfit = pos.unrealized_r != null ? pos.unrealized_r >= 0 : false;
  const stopLeft = stop < target; // long: SL on the left; short: SL on the right

  return (
    <div className="mt-2">
      <div className="relative h-[6px] rounded-full bg-raised">
        {/* filled segment entry → mark, coloured by profit/loss */}
        {markPct != null && (
          <div
            className={`absolute top-0 h-full rounded-full ${inProfit ? "bg-bull/60" : "bg-bear/60"}`}
            style={{
              left: `${Math.min(entryPct, markPct)}%`,
              width: `${Math.abs(markPct - entryPct)}%`,
            }}
          />
        )}
        {/* entry tick */}
        <span
          className="absolute top-1/2 h-[10px] w-px -translate-y-1/2 bg-mid"
          style={{ left: `${entryPct}%` }}
          title={`entry ${formatPrice(pos.entry_price)}`}
        />
        {/* live mark marker */}
        {markPct != null && (
          <span
            className="absolute top-1/2 h-[12px] w-[2px] -translate-y-1/2 bg-pulse"
            style={{ left: `${markPct}%` }}
            title={`mark ${formatPrice(pos.mark_price!)}`}
          />
        )}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9px] tabular-nums">
        <span className="text-bear">{stopLeft ? `SL ${formatPrice(pos.stop)}` : `TP ${formatPrice(pos.target)}`}</span>
        <span className="text-bull">{stopLeft ? `TP ${formatPrice(pos.target)}` : `SL ${formatPrice(pos.stop)}`}</span>
      </div>
    </div>
  );
}

function PositionTicket({
  pos,
  busy,
  onClose,
}: {
  pos: PaperPosition;
  busy: boolean;
  onClose: () => void;
}) {
  const pnlPct =
    pos.unrealized_pnl != null && Number(pos.notional_entry) > 0
      ? (Number(pos.unrealized_pnl) / Number(pos.notional_entry)) * 100
      : null;
  const tone = pnlTone(pos.unrealized_pnl);

  return (
    <div className="rounded-md border border-hair/70 bg-raised/40 px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[11.5px] tracking-[0.06em] text-hi">{pos.symbol}</span>
        <span
          className={`rounded-sm border px-1.5 py-px font-mono text-[9px] uppercase tracking-[0.1em] ${
            pos.direction === "long" ? "border-bull/40 text-bull" : "border-bear/40 text-bear"
          }`}
        >
          {pos.direction === "long" ? "▲ long" : "▼ short"}
        </span>
        <span className="rounded-sm border border-hair px-1.5 py-px font-mono text-[9px] uppercase tracking-[0.08em] text-mid">
          {pos.market_type === "perp" ? `perp ${pos.leverage}×` : "spot"}
        </span>
        {pos.mark_price != null && (
          <span className="flex items-center gap-1 font-mono text-[10px] tabular-nums text-mid">
            <span className="live-dot bg-pulse" /> {formatPrice(pos.mark_price)}
          </span>
        )}
        <button
          onClick={onClose}
          disabled={busy}
          className="ml-auto rounded-md border border-hair px-2 py-0.5 font-mono text-[9px] tracking-[0.1em] text-dim transition-colors hover:text-warn disabled:opacity-50"
        >
          close now
        </button>
      </div>

      {/* hero: unrealized PnL */}
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className={`font-mono text-[17px] font-semibold tabular-nums ${tone}`}>
          {usd(pos.unrealized_pnl, true)}
        </span>
        <span className={`font-mono text-[11px] tabular-nums ${tone}`}>
          {pnlPct != null ? `${pnlPct > 0 ? "+" : ""}${pnlPct.toFixed(2)}%` : ""}
        </span>
        <span className={`font-mono text-[11px] tabular-nums ${tone}`}>
          {pos.unrealized_r != null ? `· ${pos.unrealized_r > 0 ? "+" : ""}${pos.unrealized_r.toFixed(2)}R` : ""}
        </span>
        <span className="ml-auto font-mono text-[9px] uppercase tracking-[0.1em] text-dim">unrealized</span>
      </div>

      <PositionBar pos={pos} />

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-[10px] tabular-nums text-dim">
        <span>entry {formatPrice(pos.entry_price)}</span>
        <span>qty {qtyStr(pos.qty)}</span>
        <span>notional {usd(pos.notional_entry)}</span>
        {pos.market_type === "perp" && <span>margin {usd(pos.margin_used)}</span>}
        <span>{Number(pos.position_pct).toFixed(1)}% of acct</span>
        <span>fees {usd(pos.fees_paid)}</span>
      </div>
    </div>
  );
}

export default function PaperDeskPanel() {
  const [account, setAccount] = useState<PaperAccountView | null>(null);
  const [pending, setPending] = useState<OrderProposal[]>([]);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addAmount, setAddAmount] = useState("");
  const [orderOpen, setOrderOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [acct, props, poss] = await Promise.all([
        fetchPaperAccount(),
        fetchProposals("pending"),
        fetchPositions(),
      ]);
      setAccount(acct);
      setPending(props);
      setPositions(poss);
    } catch {
      /* backend briefly away — keep the last view */
    }
  }, []);

  const open = positions.filter((p) => p.status === "open");
  const closed = positions.filter((p) => p.status === "closed").slice(0, 6);
  const activeCount = open.length + pending.length;

  useEffect(() => {
    void refresh();
    const delay = activeCount > 0 ? POLL_LIVE_MS : POLL_IDLE_MS;
    const t = setInterval(() => void refresh(), delay);
    return () => clearInterval(t);
  }, [refresh, activeCount]);

  async function onApprove(id: string) {
    setBusy(id);
    setNotice(null);
    try {
      const r = await approveProposal(id);
      if (!r.approved) setNotice(r.reason ?? "refused");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "approve failed");
    } finally {
      setBusy(null);
      void refresh();
    }
  }

  async function onReject(id: string) {
    setBusy(id);
    setNotice(null);
    try {
      await rejectProposal(id);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "reject failed");
    } finally {
      setBusy(null);
      void refresh();
    }
  }

  async function onClose(id: string) {
    setBusy(id);
    setNotice(null);
    try {
      await closePosition(id);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "close failed");
    } finally {
      setBusy(null);
      void refresh();
    }
  }

  async function onDeposit(amount: string) {
    if (!amount || Number(amount) <= 0) return;
    setBusy("deposit");
    setNotice(null);
    try {
      const acct = await depositFunds(amount);
      setAccount(acct);
      setAddAmount("");
      setAddOpen(false);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "deposit failed");
    } finally {
      setBusy(null);
    }
  }

  async function onReset() {
    setBusy("reset");
    setNotice(null);
    try {
      await resetPaperAccount();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "reset failed");
    } finally {
      setBusy(null);
      void refresh();
    }
  }

  return (
    <div className="card dp-rise mt-4" style={{ animationDelay: "280ms" }}>
      <div className="flex items-start justify-between gap-3 border-b border-hair/70 px-5 py-3">
        <span className="min-w-0">
          <span className="micro-label block">
            paper desk · AI proposes, you approve <SourceBadge surface="paper" />
          </span>
          <span className="bn-sub mt-0.5">কাগুজে ডেস্ক — AI প্রস্তাব দেয়, অনুমোদন শুধু আপনার হাতে</span>
        </span>
        {account && (
          <span className="shrink-0 rounded-md border border-hair px-2 py-px font-mono text-[9px] tracking-[0.12em] text-mid">
            PAPER · no real keys exist
          </span>
        )}
      </div>

      {/* account strip — equity + balance are bold and coloured vs the
          starting balance (green above, red below); PnL columns keep their
          own sign colour (owner request, 2026-07-12). */}
      {account && (() => {
        const start = Number(account.starting_balance);
        const vsStart = (v: string): string => {
          const n = Number(v);
          if (!isFinite(n) || n === start) return "text-hi";
          return n > start ? "text-bull" : "text-bear";
        };
        const cells: Array<{ label: string; value: string; tone: string; bold?: boolean }> = [
          { label: "equity", value: usd(account.equity), tone: vsStart(account.equity), bold: true },
          { label: "balance", value: usd(account.balance), tone: vsStart(account.balance), bold: true },
          { label: "unrealized", value: usd(account.unrealized_pnl, true), tone: pnlTone(account.unrealized_pnl) },
          { label: "realized", value: usd(account.realized_pnl_total, true), tone: pnlTone(account.realized_pnl_total) },
          { label: "open · pending", value: `${account.n_open} · ${account.n_pending}`, tone: "text-mid" },
        ];
        return (
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 border-b border-hair/50 px-5 py-3 sm:grid-cols-5">
          {cells.map((c) => (
            <div key={c.label}>
              <span className="micro-label">{c.label}</span>
              <div className={`font-mono text-[13px] tabular-nums ${c.bold ? "font-semibold" : ""} ${c.tone}`}>{c.value}</div>
            </div>
          ))}
          {account.pricing_gaps.length > 0 && (
            <span className="col-span-full text-[10px] text-warn">
              unpriced (feed gap): {account.pricing_gaps.join(", ")}
            </span>
          )}
        </div>
        );
      })()}

      {/* account actions: add funds · new order · reset */}
      <div className="flex flex-wrap items-center gap-2 border-b border-hair/50 px-5 py-2.5">
        <button
          onClick={() => { setAddOpen((v) => !v); setOrderOpen(false); }}
          className="rounded-md border border-hair px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-mid transition-colors hover:border-pulse/40 hover:text-hi"
        >
          ＋ add funds · টাকা যোগ
        </button>
        <button
          onClick={() => { setOrderOpen((v) => !v); setAddOpen(false); }}
          className="rounded-md border border-hair px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-mid transition-colors hover:border-pulse/40 hover:text-hi"
        >
          ＋ new order · নিজের অর্ডার
        </button>
        <button
          onClick={() => void onReset()}
          disabled={busy === "reset"}
          className="ml-auto rounded-md border border-hair/60 px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-dim transition-colors hover:text-warn disabled:opacity-50"
          title="wipe the paper account back to the starting balance"
        >
          reset
        </button>
      </div>

      {/* add-funds row */}
      {addOpen && (
        <div className="flex flex-wrap items-center gap-2 border-b border-hair/50 bg-raised/20 px-5 py-2.5">
          {ADD_CHIPS.map((c) => (
            <button
              key={c}
              onClick={() => void onDeposit(c)}
              disabled={busy === "deposit"}
              className="rounded-md border border-hair px-2 py-1 font-mono text-[10px] tabular-nums text-mid transition-colors hover:border-bull/40 hover:text-bull disabled:opacity-50"
            >
              +{Number(c).toLocaleString("en-US")}
            </button>
          ))}
          <input
            value={addAmount}
            onChange={(e) => setAddAmount(e.target.value.replace(/[^0-9.]/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && void onDeposit(addAmount)}
            placeholder="custom"
            inputMode="decimal"
            className="w-[90px] rounded-md border border-hair bg-abyss/60 px-2 py-1 font-mono text-[10px] tabular-nums text-hi outline-none focus:border-pulse/50"
          />
          <button
            onClick={() => void onDeposit(addAmount)}
            disabled={busy === "deposit" || !addAmount}
            className="rounded-md border border-bull/50 px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.1em] text-bull transition-colors hover:bg-raised disabled:opacity-40"
          >
            add · যোগ
          </button>
        </div>
      )}

      {/* manual order form */}
      {orderOpen && (
        <ManualOrderForm
          busy={busy === "order"}
          maxLeverage={20}
          onSubmit={async (body) => {
            setBusy("order");
            setNotice(null);
            try {
              if (body.order_type === "market") {
                const r = await placeMarketOrder(body);
                setNotice(r.approved ? "market order filled — see open positions." : (r.reason ?? "refused"));
              } else {
                await proposeOrder(body);
                setNotice("limit order resting — it auto-fills when price reaches it.");
              }
              setOrderOpen(false);
              await refresh();
            } catch (e) {
              setNotice(e instanceof Error ? e.message : "order rejected");
            } finally {
              setBusy(null);
            }
          }}
        />
      )}

      {notice && (
        <p className="border-b border-warn/30 bg-warn/5 px-5 py-2 text-[11px] text-warn">
          {notice}
        </p>
      )}

      {/* pending proposals — the gate */}
      <div className="px-5 py-3">
        <span className="micro-label">awaiting your decision · অনুমোদনের অপেক্ষায়</span>
        {pending.length === 0 ? (
          <p className="mt-1.5 text-[11px] text-dim">
            none — the CIO (over MCP), a setup card, or your own order lands here; nothing fills without your click.
          </p>
        ) : (
          <div className="mt-2 space-y-2">
            {pending.map((p) => (
              <div key={p.id} className="rounded-md border border-hair/70 bg-raised/40 px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11px] tracking-[0.06em] text-hi">{p.symbol}</span>
                  <span className={`font-mono text-[10px] uppercase ${p.direction === "long" ? "text-bull" : "text-bear"}`}>
                    {p.direction === "long" ? "▲ long" : "▼ short"}
                  </span>
                  {p.source === "mcp" ? (
                    <span className="rounded-sm border border-[rgba(232,197,116,0.4)] px-1.5 py-px font-mono text-[8.5px] tracking-[0.1em] text-gold">
                      AI PROPOSED
                    </span>
                  ) : (
                    <span className="rounded-sm border border-hair px-1.5 py-px font-mono text-[8.5px] tracking-[0.1em] text-dim">
                      MANUAL
                    </span>
                  )}
                  <span className="ml-auto font-mono text-[9.5px] text-dim">
                    expires {dhaka.format(new Date(p.expires_at))}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-[10.5px] tabular-nums text-mid">
                  <span>entry {formatPrice(p.entry_low)}–{formatPrice(p.entry_high)}</span>
                  <span>stop <span className="text-bear">{formatPrice(p.stop)}</span></span>
                  <span>tp1 <span className="text-bull">{formatPrice(p.targets[0])}</span></span>
                  <span>risk {p.risk_pct}%</span>
                </div>
                <p className="mt-1 text-[10.5px] leading-snug text-dim">{p.thesis}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => void onApprove(p.id)}
                    disabled={busy === p.id}
                    className="rounded-md border border-bull/50 px-3 py-1 font-mono text-[10px] tracking-[0.1em] text-bull transition-colors hover:bg-raised disabled:opacity-50"
                  >
                    ✓ APPROVE · অনুমোদন
                  </button>
                  <button
                    onClick={() => void onReject(p.id)}
                    disabled={busy === p.id}
                    className="rounded-md border border-hair px-3 py-1 font-mono text-[10px] tracking-[0.1em] text-dim transition-colors hover:text-bear disabled:opacity-50"
                  >
                    ✕ reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* open positions — exchange-style tickets */}
      {open.length > 0 && (
        <div className="border-t border-hair/50 px-5 py-3">
          <span className="micro-label">open positions · চলমান পজিশন</span>
          <div className="mt-2 space-y-2">
            {open.map((x) => (
              <PositionTicket key={x.id} pos={x} busy={busy === x.id} onClose={() => void onClose(x.id)} />
            ))}
          </div>
          <p className="mt-1.5 text-[9.5px] text-dim">
            mark price + PnL update live; stop/target close deterministically against real candles — no AI.
          </p>
        </div>
      )}

      {/* recent closed */}
      {closed.length > 0 && (
        <div className="border-t border-hair/50 px-5 py-3">
          <span className="micro-label">closed · সাম্প্রতিক ফল</span>
          <div className="mt-2 space-y-1">
            {closed.map((x) => (
              <div key={x.id} className="flex flex-wrap items-center gap-x-4 font-mono text-[10.5px] tabular-nums">
                <span className="text-mid">{x.symbol}</span>
                <span className={`uppercase text-[9.5px] ${x.exit_reason === "tp" ? "text-bull" : x.exit_reason === "sl" ? "text-bear" : "text-dim"}`}>
                  {x.exit_reason}
                </span>
                <span className={pnlTone(x.realized_pnl)}>{usd(x.realized_pnl, true)}</span>
                <span className={pnlTone(x.realized_r)}>
                  {x.realized_r != null ? `${x.realized_r > 0 ? "+" : ""}${x.realized_r.toFixed(2)}R` : "—"}
                </span>
                <span className="ml-auto text-[9.5px] text-dim">
                  {x.closed_at ? dhaka.format(new Date(x.closed_at)) : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const LEV_CHIPS = [1, 2, 3, 5, 10, 20] as const;

function ManualOrderForm({
  busy,
  maxLeverage,
  onSubmit,
}: {
  busy: boolean;
  maxLeverage: number;
  onSubmit: (body: OrderBody) => void | Promise<void>;
}) {
  const [symbol, setSymbol] = useState("");
  const [direction, setDirection] = useState<"long" | "short">("long");
  const [orderType, setOrderType] = useState<"market" | "limit">("limit");
  const [marketType, setMarketType] = useState<"spot" | "perp">("spot");
  const [leverage, setLeverage] = useState(1);
  const [entry, setEntry] = useState("");
  const [stop, setStop] = useState("");
  const [tp1, setTp1] = useState("");
  const [tp2, setTp2] = useState("");
  const [risk, setRisk] = useState("1");
  const [err, setErr] = useState<string | null>(null);

  const num = (s: string) => s.trim().replace(/[^0-9.]/g, "");
  const isMarket = orderType === "market";

  function pickMarketType(m: "spot" | "perp") {
    setMarketType(m);
    if (m === "spot") setLeverage(1); // spot is always 1x (backend enforces too)
  }

  function submit() {
    setErr(null);
    let sym = symbol.trim().toUpperCase();
    if (!/USD[TC]$/.test(sym) && /^[A-Z0-9]{2,10}$/.test(sym)) sym += "USDT";
    if (!sym) return setErr("symbol required");
    if (!stop || !tp1) return setErr("stop and tp1 are required");
    // A market order fills at live price, so no entry field; a limit needs one.
    if (!isMarket && !entry) return setErr("a limit order needs an entry price");
    // For a market order the reference for geometry is the entry field if given,
    // else we can't client-check direction vs live — let the backend judge.
    const ref = isMarket ? (entry ? Number(entry) : null) : Number(entry);
    if (ref != null) {
      const s = Number(stop), t = Number(tp1);
      if (direction === "long" && !(s < ref && t > ref)) return setErr("long: stop < entry < tp1");
      if (direction === "short" && !(s > ref && t < ref)) return setErr("short: tp1 < entry < stop");
    }
    const targets = [num(tp1), tp2 ? num(tp2) : null].filter((x): x is string => !!x);
    // A market order fills at the LIVE price, so its entry_low/high are only a
    // nominal band the schema validates. Use the midpoint of stop↔tp1, which
    // is guaranteed to satisfy the geometry rule (stop < mid < tp1). A limit
    // order's band collapses to the user's chosen price.
    const nominal = isMarket
      ? String((Number(stop) + Number(tp1)) / 2)
      : num(entry);
    const levLabel = marketType === "perp" ? ` ${leverage}x` : "";
    void onSubmit({
      symbol: sym,
      direction,
      entry_low: num(nominal),
      entry_high: num(nominal),
      stop: num(stop),
      targets,
      risk_pct: num(risk) || undefined,
      order_type: orderType,
      market_type: marketType,
      leverage: marketType === "perp" ? leverage : 1,
      thesis: `manual ${orderType} ${marketType}${levLabel} — ${direction} ${sym}`,
    });
  }

  const field = "w-full rounded-md border border-hair bg-abyss/60 px-2 py-1 font-mono text-[10.5px] tabular-nums text-hi outline-none focus:border-pulse/50";
  const seg = (on: boolean, accent: string) =>
    `px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.08em] transition-colors ${on ? `bg-raised ${accent}` : "text-dim hover:text-mid"}`;

  return (
    <div className="border-b border-hair/50 bg-raised/20 px-5 py-3">
      {/* order type · market type · leverage */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-hair">
          <button onClick={() => setOrderType("market")} className={seg(isMarket, "text-pulse")}>market</button>
          <button onClick={() => setOrderType("limit")} className={seg(!isMarket, "text-pulse")}>limit</button>
        </div>
        <div className="flex overflow-hidden rounded-md border border-hair">
          <button onClick={() => pickMarketType("spot")} className={seg(marketType === "spot", "text-hi")}>spot</button>
          <button onClick={() => pickMarketType("perp")} className={seg(marketType === "perp", "text-warn")}>futures</button>
        </div>
        {marketType === "perp" && (
          <div className="flex items-center gap-1">
            <span className="micro-label">lev</span>
            {LEV_CHIPS.filter((l) => l <= maxLeverage).map((l) => (
              <button key={l} onClick={() => setLeverage(l)}
                className={`rounded-md border px-1.5 py-0.5 font-mono text-[10px] tabular-nums transition-colors ${
                  leverage === l ? "border-warn/50 text-warn" : "border-hair text-dim hover:text-mid"
                }`}>
                {l}×
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-0.5">
          <span className="micro-label">symbol</span>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="BTCUSDT" className={`${field} w-[104px]`} />
        </label>
        <div className="flex overflow-hidden rounded-md border border-hair">
          {(["long", "short"] as const).map((d) => (
            <button key={d} onClick={() => setDirection(d)}
              className={seg(direction === d, d === "long" ? "text-bull" : "text-bear")}>
              {d === "long" ? "▲ long" : "▼ short"}
            </button>
          ))}
        </div>
        {!isMarket && (
          <label className="flex flex-col gap-0.5">
            <span className="micro-label">entry (limit)</span>
            <input value={entry} onChange={(e) => setEntry(e.target.value)} inputMode="decimal"
              placeholder="price" className={`${field} w-[92px]`} />
          </label>
        )}
        <label className="flex flex-col gap-0.5">
          <span className="micro-label">stop</span>
          <input value={stop} onChange={(e) => setStop(e.target.value)} inputMode="decimal"
            placeholder="SL" className={`${field} w-[92px]`} />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="micro-label">tp1</span>
          <input value={tp1} onChange={(e) => setTp1(e.target.value)} inputMode="decimal"
            placeholder="target" className={`${field} w-[92px]`} />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="micro-label">tp2 · opt</span>
          <input value={tp2} onChange={(e) => setTp2(e.target.value)} inputMode="decimal"
            placeholder="—" className={`${field} w-[80px]`} />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="micro-label">risk %</span>
          <input value={risk} onChange={(e) => setRisk(e.target.value)} inputMode="decimal"
            className={`${field} w-[56px]`} />
        </label>
        <button onClick={submit} disabled={busy}
          className="rounded-md border border-pulse/50 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-pulse transition-colors hover:bg-raised disabled:opacity-50">
          {isMarket ? "buy/sell now · এখনই" : "place · রাখো"}
        </button>
      </div>
      {err && <p className="mt-1.5 text-[10px] text-bear">{err}</p>}
      <p className="mt-1.5 text-[9.5px] leading-snug text-dim">
        {isMarket
          ? "Market fills at once at the live price."
          : "Limit rests at your price and auto-fills when price reaches it — no approval needed for your own order."}
        {marketType === "perp" && " Futures shows margin used; liquidation is not modeled (a later Fable pass)."}
        <span className="font-bn"> {isMarket ? "মার্কেট — এখনই লাইভ দামে।" : "লিমিট — দাম ছুঁলে নিজে থেকেই পূরণ হবে।"}</span>
      </p>
    </div>
  );
}
