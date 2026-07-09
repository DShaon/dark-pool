/** Journal store — single-user P1 persistence in localStorage (`dp:journal`).
 *  A read saved from the Desk Verdict lands here as an OPEN trade; you grade it
 *  later (tp / sl / invalidated). Stats are computed from graded trades only.
 *
 *  Storage is display-string prices (no float math here) + UTC timestamps
 *  (invariant 3); the journal page converts times to Asia/Dhaka for display.
 *  Server-side/DB persistence arrives later without changing call sites.
 */

export type Outcome = "open" | "tp" | "sl" | "invalidated";
export type Direction = "long" | "short" | "no_trade";

export type JournalTrade = {
  id: string;
  savedAt: string; // ISO UTC
  symbol: string;
  dir: Direction;
  conviction: number; // 1–5
  entryLow: string | null;
  entryHigh: string | null;
  stop: string | null;
  target: string | null; // TP1
  targetRR: number | null; // planned R:R to TP1
  thesis: string;
  source: "quick_read" | "manual";
  outcome: Outcome;
};

export type NewTrade = Omit<JournalTrade, "id" | "savedAt" | "outcome">;

const KEY = "dp:journal";

function newId(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  } catch {
    /* fall through */
  }
  return `t_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
}

export function loadJournal(): JournalTrade[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as JournalTrade[];
  } catch {
    /* corrupted storage → empty */
  }
  return [];
}

function persist(list: JournalTrade[]): JournalTrade[] {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage full/blocked — caller still gets the in-memory list */
  }
  return list;
}

/** Prepend a new OPEN trade; returns the updated list (newest first). */
export function addTrade(t: NewTrade): JournalTrade[] {
  const entry: JournalTrade = {
    ...t,
    id: newId(),
    savedAt: new Date().toISOString(),
    outcome: "open",
  };
  return persist([entry, ...loadJournal()]);
}

export function setOutcome(id: string, outcome: Outcome): JournalTrade[] {
  return persist(loadJournal().map((t) => (t.id === id ? { ...t, outcome } : t)));
}

export function removeTrade(id: string): JournalTrade[] {
  return persist(loadJournal().filter((t) => t.id !== id));
}

/** Realized R for a graded trade: TP hit ⇒ planned R:R to TP1; SL hit ⇒ −1R.
 *  Open / invalidated trades are not graded (return null). */
export function tradeR(t: JournalTrade): number | null {
  if (t.outcome === "tp") return t.targetRR ?? null;
  if (t.outcome === "sl") return -1;
  return null;
}

export type JournalStats = {
  total: number;
  open: number;
  graded: number;
  winRatePct: number | null;
  avgR: number | null;
  totalR: number | null;
};

export function computeStats(trades: JournalTrade[]): JournalStats {
  const graded = trades.filter((t) => t.outcome === "tp" || t.outcome === "sl");
  const rs = graded.map(tradeR).filter((r): r is number => r !== null);
  const wins = graded.filter((t) => t.outcome === "tp").length;
  const sum = rs.reduce((a, b) => a + b, 0);
  return {
    total: trades.length,
    open: trades.filter((t) => t.outcome === "open").length,
    graded: graded.length,
    winRatePct: graded.length ? (wins / graded.length) * 100 : null,
    avgR: rs.length ? sum / rs.length : null,
    totalR: rs.length ? sum : null,
  };
}
