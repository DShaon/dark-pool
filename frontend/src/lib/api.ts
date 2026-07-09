/** Typed client for the DARKPOOL backend.
 *  Contract: Decimal price fields arrive as JSON *strings* (precision-safe);
 *  float analytics arrive as numbers. We never do arithmetic on price strings —
 *  parseFloat happens only at the chart/display boundary. */

export const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Kline = {
  open_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  close_time: string;
};

export type StructureEvent = {
  kind: "BOS" | "CHoCH";
  direction: "bullish" | "bearish";
  level: string;
  time: string;
};

export type ZoneOut = {
  kind: "order_block" | "fvg";
  side: "bullish" | "bearish";
  top: string;
  bottom: string;
  mitigated: boolean;
  time: string;
};

export type LevelOut = {
  kind: "PDH" | "PDL" | "PWH" | "PWL" | "EQH" | "EQL";
  price: string;
  state: "intact" | "swept" | "broken";
};

export type TimeframeAnalysis = {
  tf: string;
  last_close: string;
  structure: {
    trend: "bullish" | "bearish" | "range";
    last_event: StructureEvent | null;
  };
  premium_discount: "premium" | "discount" | "equilibrium";
  swings: { time: string; price: string; kind: "high" | "low" }[];
  order_blocks: ZoneOut[];
  fvgs: ZoneOut[];
  equal_levels: LevelOut[];
  indicators: Record<string, number | null>;
};

export type MarketBrief = {
  version: string;
  symbol: string;
  generated_at: string;
  timeframes: Record<string, TimeframeAnalysis>;
  daily_levels: LevelOut[];
  derivatives: {
    funding_rate: number;
    funding_regime: string;
    mark_price: number;
    open_interest: number | null;
    oi_change_24h_pct: number | null;
    long_short_ratio: number | null;
  } | null;
  sentiment: { fear_greed: number; label: string } | null;
  alignment: { score: number; bias: "long" | "short" | "mixed"; per_tf: Record<string, string> };
  gaps: string[];
};

export type QuickRead = {
  direction: "long" | "short" | "no_trade";
  conviction: number; // 1–5
  entry_zone: { low: string; high: string } | null;
  stop_loss: string | null;
  targets: { price: string; rr: number }[];
  thesis: string;
  failure_mode: string;
  thesis_bn: string | null;
  failure_mode_bn: string | null;
  invalidation: { price: string; condition: string } | null;
  evidence: string[];
};

export type QuickReadResponse = {
  symbol: string;
  generated_at: string;
  brief_generated_at: string;
  model_id: string;
  status: "ok" | "degraded";
  reason: string | null;
  read: QuickRead | null;
};

export type Mandate = "trend" | "contrarian" | "derivatives" | "risk";

export type AnalystThesis = {
  mandate: Mandate;
  model_id: string;
  read: QuickRead;
};

export type DroppedAnalyst = { mandate: Mandate; reason: string };

/** Full Desk (tier 2) — the mandate-analyst panel. `tally` is a display count of
 *  directions; the CIO's single synthesized verdict + calibrated confidence are
 *  a separate Fable-tier step (not in this payload yet). */
export type DeskPanelResponse = {
  symbol: string;
  generated_at: string;
  brief_generated_at: string;
  theses: AnalystThesis[];
  dropped: DroppedAnalyst[];
  tally: Record<string, number>;
  status: "ok" | "degraded";
  reason: string | null;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`backend HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`backend HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export const fetchKlines = (symbol: string, interval: string, limit = 200) =>
  get<Kline[]>(`/klines/${symbol}?interval=${interval}&limit=${limit}`);

export const fetchBrief = (symbol: string) => get<MarketBrief>(`/brief/${symbol}`);

export const fetchQuickRead = (symbol: string, force = false) =>
  get<QuickReadResponse>(`/quickread/${symbol}${force ? "?force=true" : ""}`);

export const fetchDesk = (symbol: string, force = false) =>
  get<DeskPanelResponse>(`/desk/${symbol}${force ? "?force=true" : ""}`);

export type AlertTone = "bull" | "bear" | "warn" | "dim" | "pulse";
export type AlertEvent = {
  kind: string;
  symbol: string;
  timeframe: string | null;
  tone: AlertTone;
  message: string;
  message_bn: string;
  at: string;
  ref: string | null;
};
export type AlertFeedResponse = { symbol: string; generated_at: string; alerts: AlertEvent[] };

export const fetchAlerts = (symbol: string) => get<AlertFeedResponse>(`/alerts/${symbol}`);

export type ScannerMode = "manual" | "active";

export const fetchScannerMode = () => get<{ mode: ScannerMode }>("/monitor/mode");
export const setScannerMode = (mode: ScannerMode) =>
  post<{ mode: ScannerMode }>("/monitor/mode", { mode });

export const syncWatchlist = (symbols: string[]) =>
  post<{ symbols: string[] }>("/monitor/watchlist", { symbols });

export type GradeResponse = {
  symbol: string;
  outcome: "tp" | "sl" | "open";
  hit_at: string | null;
  candles_checked: number;
};

/** Deterministic outcome check (P3 · FR-6) — did price reach target or stop
 *  since the trade was saved? No AI; pure candle-walk on the backend. */
export const fetchGrade = (
  symbol: string,
  direction: "long" | "short",
  stop: string,
  target: string,
  since: string,
) =>
  get<GradeResponse>(
    `/grade/${symbol}?direction=${direction}&stop=${encodeURIComponent(stop)}` +
      `&target=${encodeURIComponent(target)}&since=${encodeURIComponent(since)}`,
  );

/** Display-only price formatting (strings in, strings out — no float math). */
export function formatPrice(raw: string | number): string {
  const s = typeof raw === "number" ? String(raw) : raw;
  const [intRaw, fracRaw = ""] = s.split(".");
  const frac = fracRaw.replace(/0+$/, "");
  const maxFrac = intRaw.replace("-", "").length >= 3 ? 2 : Math.min(frac.length, 6);
  const intFmt = intRaw.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fracFmt = frac.slice(0, maxFrac);
  return fracFmt ? `${intFmt}.${fracFmt}` : intFmt;
}
