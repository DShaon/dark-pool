/** Typed client for the DARKPOOL backend.
 *  Contract: Decimal price fields arrive as JSON *strings* (precision-safe);
 *  float analytics arrive as numbers. We never do arithmetic on price strings —
 *  parseFloat happens only at the chart/display boundary. */

export const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// Shared-secret bearer token (single-user v1, ADR-0009). Unset in dev — the
// backend's require_auth is a no-op when API_TOKEN is empty. Set both
// NEXT_PUBLIC_API_TOKEN (frontend) and API_TOKEN (backend) to the SAME
// value once deployed publicly, so a stranger with the URL can't burn your
// LLM quota or place paper trades.
const AUTH_HEADERS: HeadersInit = process.env.NEXT_PUBLIC_API_TOKEN
  ? { Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_TOKEN}` }
  : {};

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

/** Full Desk (tier 2) — the mandate-analyst panel. `tally` is a display count
 *  of directions; the CIO's synthesized verdict lives on /plan (below). */
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

/* ── CIO TradePlan (§B5 · ADR-0015) — the desk's one call ── */

export type ConsensusState = "aligned" | "split" | "contested";

export type SeatVoteOut = { direction: "long" | "short" | "no_trade"; conviction: number };

export type DivergenceReport = {
  consensus_state: ConsensusState;
  plurality_direction: "long" | "short" | "no_trade";
  votes: Record<string, number>;
  conviction_weighted: Record<string, number>;
  votes_by_seat: Record<string, SeatVoteOut>;
  entry_cluster: boolean | null;
  stop_cluster: boolean | null;
  conviction_spread: number;
  notes: string[];
};

export type ConfidenceBreakdown = {
  value: number; // the published, ADR-0007-calibrated number
  checklist: number;
  agreement: number;
  components: Record<string, number>;
  excluded: string[];
  state_base: number;
  weighted_vote_share: number;
  // Recalibration (ADR-0018) — false/0.5/{} until outcomes exist.
  calibrated: boolean;
  blend_w: number;
  seat_weights: Record<string, number>;
};

export type SizingOut = {
  risk_pct: number;
  stop_distance_pct: number;
  position_pct: number;
  capped: boolean;
  implied_leverage: number;
};

export type TradePlan = {
  symbol: string;
  direction: "long" | "short" | "no_trade";
  consensus_state: ConsensusState;
  confidence: ConfidenceBreakdown;
  divergence: DivergenceReport;
  entry_zone: { low: string; high: string } | null;
  confirmation: string[];
  stop_loss: string | null;
  targets: { price: string; rr: number }[];
  invalidation: { price: string; condition: string } | null;
  sizing: SizingOut | null;
  thesis: string;
  failure_mode: string;
  alternative_scenario: string;
  thesis_bn: string | null;
  failure_mode_bn: string | null;
  evidence: string[];
  built_from: Mandate[];
  synthesizer: string;
};

export type TradePlanResponse = {
  symbol: string;
  generated_at: string;
  brief_generated_at: string;
  status: "ok" | "degraded";
  reason: string | null;
  plan: TradePlan | null;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", headers: AUTH_HEADERS });
  if (!res.ok) throw new Error(`backend HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...AUTH_HEADERS },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `backend HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { method: "DELETE", headers: AUTH_HEADERS });
  if (!res.ok) {
    let detail = `backend HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const fetchKlines = (symbol: string, interval: string, limit = 200) =>
  get<Kline[]>(`/klines/${symbol}?interval=${interval}&limit=${limit}`);

export const fetchBrief = (symbol: string) => get<MarketBrief>(`/brief/${symbol}`);

export const fetchQuickRead = (symbol: string, force = false) =>
  get<QuickReadResponse>(`/quickread/${symbol}${force ? "?force=true" : ""}`);

export const fetchDesk = (symbol: string, force = false) =>
  get<DeskPanelResponse>(`/desk/${symbol}${force ? "?force=true" : ""}`);

/** The CIO's synthesized plan. Never force the panel from here — /plan rides
 *  the desk cache; a fresh desk run invalidates the plan automatically. */
export const fetchPlan = (symbol: string, force = false) =>
  get<TradePlanResponse>(`/plan/${symbol}${force ? "?force=true" : ""}`);

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

/* ── AI scenario path (ADR-0017 §2) — sequence opinion, not a forecast ── */

export type Waypoint = {
  level_ref: string;
  label: string | null;
  price: string | null;
  bar_offset: number | null;
};
export type ScenarioPath = {
  direction: "long" | "short" | "neutral";
  waypoints: Waypoint[];
  narrative: string;
  narrative_bn: string | null;
  evidence: string[];
};
export type ScenarioResponse = {
  symbol: string;
  generated_at: string;
  status: "ok" | "unavailable";
  reason: string | null;
  model_id: string | null;
  path: ScenarioPath | null;
};

export const fetchScenario = (symbol: string, force = false) =>
  get<ScenarioResponse>(`/scenario/${symbol}${force ? "?force=true" : ""}`);

/* ── Setup variants (FR-4 fan · ADR-0019 + ADR-0022 structure-aware) ── */

export type SetupVariant = {
  key: "scalp" | "intraday" | "swing" | "spot" | "grid" | "options";
  venue: string;
  style: string;
  leverage: number;
  anchor_tf: string;
  direction: "long" | "short" | "neutral";
  tradeable: boolean;
  gradeable: boolean;
  reason: string | null;
  entry_low: string | null;
  entry_high: string | null;
  stop: string | null;
  targets: { price: string; rr: number }[];
  edge: string;
  edge_bn: string;
  // ADR-0022: "structure" = entry anchored on a real order block / FVG;
  // "atr_fallback" = no zone in range, honest ATR rule. quality is null on
  // grid/options/untradeable. confluence = the exact reasons that fired.
  entry_kind: "structure" | "atr_fallback";
  quality: "high" | "medium" | "low" | null;
  confluence: string[];
};
export type SetupsResponse = {
  symbol: string;
  generated_at: string;
  brief_generated_at: string;
  bias: "long" | "short" | "mixed";
  variants: SetupVariant[];
};

export const fetchSetups = (symbol: string) => get<SetupsResponse>(`/setups/${symbol}`);

/* ── Lessons (ADR-0019) — post-mortems + per-variant performance ── */

export type LessonOutcome = "tp" | "sl" | "invalidated";
export type VariantStats = { n: number; wins: number; losses: number; win_rate: number | null };
export type LessonsDigest = {
  n_records: number;
  by_variant: Record<string, VariantStats>;
  top_tags: [string, number][];
  recent_notes: string[];
};

export const fetchLessons = () => get<LessonsDigest>("/lessons");
export const fetchLessonTags = () =>
  get<{ tags: Record<string, { en: string; bn: string }> }>("/lessons/tags");

/** Report a graded trade (win or loss) to the lessons log. Re-posting the
 *  same (symbol, closed_at) UPDATES the record — refining a post-mortem note
 *  is expected, never a duplicate. */
export const postLesson = (body: {
  symbol: string;
  source: "cio" | "setup" | "quick_read" | "manual";
  variant: string | null;
  direction: "long" | "short";
  outcome: LessonOutcome;
  tags: string[];
  note: string;
  closed_at: string;
}) => post<{ ok: boolean; n_records: number }>("/lessons", body);

/* ── Model roster (ADR-0016) — user-managed providers, keys, role assignments ── */

export type RoleAssignment = {
  provider: string | null;
  model: string | null;
  temperature: number | null;
  max_tokens: number | null;
  source: "user" | "yaml";
  ready: boolean;
};
export type RosterProvider = {
  name: string;
  base_url: string;
  api_key: string; // masked (····last4) or "env" — never the full key
  source: "user" | "yaml";
  editable: boolean;
};
export type RosterView = {
  roles: string[];
  assignments: Record<string, RoleAssignment>;
  providers: RosterProvider[];
};

/* ── Confidence recalibration (ADR-0018) ── */

export type SeatScore = { eff_n: number; eff_hits: number; accuracy: number; weight: number };
export type CurveBucket = { lo: number; hi: number; n: number; wins: number; win_rate: number | null };
export type CalibrationView = {
  n_outcomes: number;
  eff_n: number;
  blend_w: number;
  blend_active: boolean;
  seats: Record<string, SeatScore>;
  brier_blended: number | null;
  brier_checklist: number | null;
  brier_agreement: number | null;
  curve: CurveBucket[];
};

export const fetchCalibration = () => get<CalibrationView>("/calibration");

/** Report a graded, CIO-plan-sourced trade so recalibration can learn from it.
 *  Idempotent server-side on (symbol, closed_at). */
export const postOutcome = (body: {
  symbol: string;
  direction: "long" | "short";
  outcome: "tp" | "sl";
  confidence: number;
  checklist: number;
  agreement: number;
  seat_votes: Record<string, SeatVoteOut>;
  closed_at: string;
}) => post<{ added: boolean; n_outcomes: number; blend_w: number }>("/outcomes", body);

export const fetchRoster = () => get<RosterView>("/models/roster");
export const testModel = (base_url: string, api_key: string, model: string) =>
  post<{ ok: boolean; message: string }>("/models/test", { base_url, api_key, model });
export const addProvider = (name: string, base_url: string, api_key: string) =>
  post<{ ok: boolean; reachable: boolean; note: string | null }>("/models/provider", {
    name,
    base_url,
    api_key,
  });
export const deleteProvider = (name: string) => del<{ ok: boolean }>(`/models/provider/${name}`);
export const setModelRole = (
  role: string,
  provider: string,
  model: string,
  temperature?: number,
  max_tokens?: number,
) => post<{ ok: boolean }>("/models/role", { role, provider, model, temperature, max_tokens });
export const deleteModelRole = (role: string) => del<{ ok: boolean }>(`/models/role/${role}`);

/* ── Backtesting (P5 · ADR-0020) — walk-forward replay of the setup variants ── */

export type MonteCarloOut = {
  iterations: number;
  seed: number;
  total_r_p5: number;
  total_r_p25: number;
  total_r_p50: number;
  total_r_p75: number;
  total_r_p95: number;
  max_dd_p50: number;
  max_dd_p95: number;
  prob_loss: number;
};
export type BacktestVariantResult = {
  key: "scalp" | "intraday" | "swing" | "spot";
  n_trades: number;
  n_wins: number;
  n_losses: number;
  n_open_excluded: number;
  win_rate: number | null;
  avg_r: number | null;
  total_r: number;
  profit_factor: number | null;
  max_drawdown_r: number;
  max_consecutive_losses: number;
  equity_r: number[];
  monte_carlo: MonteCarloOut | null;
  mc_note: string | null;
};
export type BacktestAssumptions = {
  decision_interval: string;
  exit_interval: string;
  warmup_bars: number;
  fill_model: string;
  fill_bar_rule: string;
  both_touch_rule: string;
  gap_rule: string;
  funding_note: string;
  fees_bps_per_side: Record<string, number>;
  slippage_bps_per_side: number;
  mc_iterations: number;
  mc_seed: number;
  mc_min_trades: number;
};
export type BacktestReport = {
  symbol: string;
  requested_days: number;
  window_start: string;
  window_end: string;
  generated_at: string;
  n_decisions: number;
  variants: BacktestVariantResult[];
  assumptions: BacktestAssumptions;
  notes: string[];
};
export type BacktestJobStatus = {
  state: "idle" | "running" | "done" | "error";
  symbol: string | null;
  days: number | null;
  progress: number;
  message: string | null;
};

/* ── Paper broker (P5 · ADR-0021) — propose is AI/UI, approve is HUMAN-ONLY ── */

export type BrokerAuditEvent = {
  at: string;
  actor: "mcp" | "ui" | "system";
  action: string;
  detail: string | null;
};
export type OrderType = "market" | "limit";
export type MarketType = "spot" | "perp";
export type OrderProposal = {
  id: string;
  symbol: string;
  direction: "long" | "short";
  entry_low: string;
  entry_high: string;
  stop: string;
  targets: string[];
  risk_pct: string;
  thesis: string;
  source: "mcp" | "ui" | "system";
  status: "pending" | "filled" | "rejected" | "expired";
  created_at: string;
  expires_at: string;
  position_id: string | null;
  order_type: OrderType | null;
  market_type: MarketType;
  leverage: number;
  audit: BrokerAuditEvent[];
};
export type PaperPosition = {
  id: string;
  proposal_id: string;
  symbol: string;
  direction: "long" | "short";
  qty: string;
  entry_price: string;
  stop: string;
  target: string;
  notional_entry: string;
  fees_paid: string;
  risk_pct: string;
  position_pct: string;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
  exit_price: string | null;
  exit_reason: "tp" | "sl" | "manual" | null;
  realized_pnl: string | null;
  realized_r: number | null;
  // ADR-0023: leverage/margin (no liquidation).
  market_type: MarketType;
  leverage: number;
  margin_used: string;
  // Live-quoted on OPEN positions by GET /broker/positions (owner request);
  // null on closed positions and on a pricing gap (never a guessed number).
  mark_price: string | null;
  unrealized_pnl: string | null;
  unrealized_r: number | null;
  audit: BrokerAuditEvent[];
};
export type PaperAccountView = {
  starting_balance: string;
  balance: string;
  equity: string;
  unrealized_pnl: string;
  realized_pnl_total: string;
  n_open: number;
  n_closed: number;
  n_pending: number;
  priced_at: string;
  pricing_gaps: string[];
};
export type ApproveResult = {
  approved: boolean;
  reason: string | null;
  proposal: OrderProposal;
  position: PaperPosition | null;
};

export type OrderBody = {
  symbol: string;
  direction: "long" | "short";
  entry_low: string;
  entry_high: string;
  stop: string;
  targets: string[];
  thesis: string;
  risk_pct?: string;
  order_type?: OrderType;
  market_type?: MarketType;
  leverage?: number;
};
export const proposeOrder = (body: OrderBody) =>
  post<OrderProposal>("/broker/propose", body);
/** Manual MARKET order — fills at once at the live price (ADR-0023). */
export const placeMarketOrder = (body: OrderBody) =>
  post<ApproveResult>("/broker/market", body);
export const fetchProposals = (status?: string) =>
  get<OrderProposal[]>(`/broker/proposals${status ? `?status=${status}` : ""}`);
export const approveProposal = (id: string) =>
  post<ApproveResult>(`/broker/approve/${id}`, {});
export const rejectProposal = (id: string) =>
  post<OrderProposal>(`/broker/reject/${id}`, {});
export const fetchPositions = (status?: string) =>
  get<PaperPosition[]>(`/broker/positions${status ? `?status=${status}` : ""}`);
export const closePosition = (id: string) =>
  post<PaperPosition>(`/broker/close/${id}`, {});
export const fetchPaperAccount = () => get<PaperAccountView>("/broker/account");
export const resetPaperAccount = () =>
  post<{ ok: boolean }>("/broker/reset", {});
export const depositFunds = (amount: string) =>
  post<PaperAccountView>("/broker/deposit", { amount });

export const startBacktest = (symbol: string, days?: number) =>
  post<{ started: boolean; symbol: string; days: number }>(
    `/backtest/${symbol}${days ? `?days=${days}` : ""}`,
    {},
  );
export const fetchBacktestStatus = () => get<BacktestJobStatus>("/backtest/status");
export const fetchBacktestReport = (symbol: string) =>
  get<BacktestReport>(`/backtest/${symbol}`);

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
