/** Data provenance registry (ADR-0017 §5) — where every displayed number comes
 *  from. Three kinds:
 *    vendor  — fetched from a named external source (which, how fresh)
 *    engine  — computed deterministically by our quant engine (no AI)
 *    ai      — produced by a model, evidence-locked / guard-railed in code
 *
 *  The user asked to verify the origin of ANY data on the desk in one click.
 *  Every data-bearing surface registers an entry here; a `SourceBadge` renders
 *  it. AI entries take a runtime `detail` (the actual model id / synthesizer).
 */

export type ProvKind = "vendor" | "engine" | "ai";

export type Provenance = {
  kind: ProvKind;
  en: string;
  bn: string;
};

export const PROVENANCE: Record<string, Provenance> = {
  ticker: {
    kind: "vendor",
    en: "Live price — Binance spot via our WebSocket relay (sub-second), with a REST poll as a resync backstop. Forex uses Twelve Data REST (60s).",
    bn: "লাইভ দাম — ক্রিপ্টো বাইন্যান্স স্পট থেকে ওয়েবসকেটে (সেকেন্ডেরও কমে), REST শুধু ব্যাকআপ। ফরেক্সে Twelve Data (৬০ সেকেন্ড)।",
  },
  chart: {
    kind: "vendor",
    en: "Candles — Binance spot klines (crypto) or Twelve Data (forex). EMA/volume drawn from those candles. Overlays (plan, OB/FVG, liquidity) are drawn from the brief; the gold scenario path is AI (labelled).",
    bn: "ক্যান্ডেল — বাইন্যান্স (ক্রিপ্টো) বা Twelve Data (ফরেক্স)। EMA/ভলিউম ওই ক্যান্ডেল থেকেই। প্ল্যান/OB/FVG ব্রিফ থেকে; সোনালি দৃশ্যকল্প-পথ AI (চিহ্নিত)।",
  },
  signals: {
    kind: "engine",
    en: "Every chip is computed by our deterministic quant engine from the candles — trend/structure, RSI, EMA stack, VWAP side, ATR%, nearest liquidity. No AI, no guessing.",
    bn: "প্রতিটি চিপ আমাদের নিজস্ব ইঞ্জিন ক্যান্ডেল থেকে হিসাব করে — ট্রেন্ড, RSI, EMA, VWAP, ATR, কাছের লিকুইডিটি। কোনো AI নেই।",
  },
  structure: {
    kind: "engine",
    en: "Swings, BOS/CHoCH, order blocks, FVGs, premium/discount — all computed in code from the candles (Smart Money Concepts). Deterministic; identical inputs give identical output.",
    bn: "সুইং, BOS/CHoCH, অর্ডার ব্লক, FVG, প্রিমিয়াম/ডিসকাউন্ট — সবই কোডে ক্যান্ডেল থেকে হিসাব। একই ইনপুটে সবসময় একই ফল।",
  },
  derivatives: {
    kind: "vendor",
    en: "Funding rate, open interest and long/short ratio from Binance USDⓈ-M futures. Crypto only — forex spot has no perps.",
    bn: "ফান্ডিং, ওপেন ইন্টারেস্ট, লং/শর্ট অনুপাত — বাইন্যান্স ফিউচার্স থেকে। শুধু ক্রিপ্টো; ফরেক্স স্পটে পার্প নেই।",
  },
  fear_greed: {
    kind: "vendor",
    en: "Crypto Fear & Greed index from alternative.me (0–100). A crowd-sentiment gauge, crypto-only.",
    bn: "ক্রিপ্টো ফিয়ার ও গ্রিড সূচক — alternative.me থেকে (০–১০০)। ভিড়ের মেজাজের মাপ, শুধু ক্রিপ্টো।",
  },
  alignment: {
    kind: "engine",
    en: "Multi-timeframe alignment score — our engine reads the 15m/1h/4h structure and averages their direction. Deterministic, not an opinion.",
    bn: "টাইমফ্রেম ঐক্য স্কোর — ইঞ্জিন ১৫মি/১ঘ/৪ঘ স্ট্রাকচার পড়ে গড় করে। মতামত নয়, হিসাব।",
  },
  quickread: {
    kind: "ai",
    en: "One AI model reads the deterministic Market Brief and returns a fast call. Every number it cites must exist in the brief (evidence-locked in code) or the read is rejected.",
    bn: "একটি AI মডেল ব্রিফ পড়ে দ্রুত রায় দেয়। যে সংখ্যা বলে তা ব্রিফে থাকতেই হবে (কোডে যাচাই), নইলে বাতিল।",
  },
  desk: {
    kind: "ai",
    en: "Four AI analysts (Trend/Contrarian/Derivatives/Risk) read the SAME brief with different mandates. Each is evidence-locked; a failing one is dropped, never faked.",
    bn: "চার AI বিশ্লেষক একই ব্রিফ ভিন্ন দৃষ্টিতে পড়ে। প্রত্যেকে প্রমাণে বাঁধা; ব্যর্থ হলে বাদ, বানানো নয়।",
  },
  cio: {
    kind: "ai",
    en: "The CIO synthesises the four analysts into one call. It may only use levels the analysts published (guard-railed in code); R:R, confidence (ADR-0007) and size are computed deterministically — not by the model.",
    bn: "CIO চার বিশ্লেষককে এক রায়ে মেলায়। শুধু বিশ্লেষকদের দেওয়া লেভেল ব্যবহার করতে পারে (কোডে সীমিত); R:R, আস্থা, সাইজ কোডে হিসাব — মডেল নয়।",
  },
  scenario: {
    kind: "ai",
    en: "A sequence OPINION, not a forecast. The AI only picks WHICH real, already-computed levels price may visit and in what order — it never invents a price. Drawn gold, over real brief levels.",
    bn: "এটি ক্রম-অনুমান, ভবিষ্যদ্বাণী নয়। AI শুধু ঠিক করে কোন বাস্তব লেভেল কোন ক্রমে ছোঁয়া হতে পারে — কোনো দাম বানায় না।",
  },
  setups: {
    kind: "engine",
    en: "Structure-aware setup variants computed by our engine from the brief (no AI). Each style first hunts a REAL unmitigated order block or fair-value-gap on its own timeframe and anchors the entry there — stop beyond genuine invalidation (zone edge or last swing), targets at real liquidity (equal highs/lows, opposing zones). When no zone is within reach it falls back to a plain ATR rule — each card says which, plus a quality grade (high/medium/low) and the exact confluence reasons that fired. Saved trades grade against real candles and feed the lessons loop.",
    bn: "আমাদের ইঞ্জিন ব্রিফ থেকে কাঠামো বুঝে সেটআপ বানায় (AI নয়)। প্রতিটি স্টাইল আগে নিজের টাইমফ্রেমে আসল অর্ডার ব্লক বা FVG খোঁজে আর সেখানেই এন্ট্রি বসায় — স্টপ আসল ইনভ্যালিডেশনের ওপারে, টার্গেট আসল লিকুইডিটিতে। কাছে জোন না থাকলে সাধারণ ATR নিয়মে ফিরে যায় — প্রতিটি কার্ড বলে দেয় কোনটা, সাথে মান (উচ্চ/মাঝারি/নিম্ন) ও কারণগুলো। সেভ করা ট্রেড আসল ক্যান্ডেলে যাচাই হয়ে শিক্ষার ভান্ডারে জমা হয়।",
  },
  tape: {
    kind: "engine",
    en: "Desk Tape — deterministic conditions our engine finds in the brief (structure breaks, sweeps, funding/OI extremes, fresh zones). No AI; each is a computed fact.",
    bn: "ডেস্ক টেপ — ইঞ্জিন ব্রিফে যেসব অবস্থা পায় (স্ট্রাকচার ব্রেক, সুইপ, ফান্ডিং চরম, নতুন জোন)। AI নয়, হিসাব করা তথ্য।",
  },
  watchlist: {
    kind: "vendor",
    en: "Each tile's price + 24h sparkline from Binance klines (crypto tiles also carry the live WebSocket tick). Forex tiles are REST-polled (Twelve Data).",
    bn: "প্রতিটি টাইলের দাম ও ২৪ঘ স্পার্কলাইন বাইন্যান্স থেকে (ক্রিপ্টোতে লাইভ টিকও)। ফরেক্স টাইল Twelve Data REST।",
  },
  journal: {
    kind: "engine",
    en: "Your saved trades (this browser) graded deterministically against real Binance candles — did price reach target or stop. Stats (win rate, avg R) computed from those outcomes.",
    bn: "আপনার সেভ করা ট্রেড (এই ব্রাউজারে) বাস্তব ক্যান্ডেলের সাথে মিলিয়ে যাচাই — টার্গেট না স্টপ ছুঁলো। স্ট্যাট ওই ফল থেকে।",
  },
  feed: {
    kind: "engine",
    en: "Background scanner conditions across your watchlist — the same deterministic rules as the tape, logged over time in Active mode. No AI.",
    bn: "ব্যাকগ্রাউন্ড স্ক্যানার আপনার তালিকায় যা পায় — টেপের মতোই নিয়ম, অ্যাক্টিভ মোডে সময় ধরে লগ। AI নয়।",
  },
  paper: {
    kind: "engine",
    en: "Paper trading desk — simulated balance, REAL Binance prices, fees and slippage charged both ways. The AI can only PROPOSE; approving is a human-only button (no approval capability exists on any AI surface — ADR-0021). No real exchange keys exist anywhere.",
    bn: "কাগুজে ট্রেডিং ডেস্ক — টাকা নকল, দাম আসল (বাইন্যান্স), ফি-ও কাটা হয়। AI শুধু প্রস্তাব দিতে পারে; অনুমোদনের বোতাম কেবল আপনার। আসল এক্সচেঞ্জ চাবি কোথাও নেই।",
  },
  backtest: {
    kind: "engine",
    en: "Walk-forward replay of the SAME setup rules over real Binance history — no AI, no lookahead, conservative fills, every R net of fees. Monte Carlo resampling puts confidence intervals on the result. Past regime, not a promise.",
    bn: "একই সেটআপ-নিয়ম বাস্তব ইতিহাসের ওপর আবার চালানো — AI নয়, ভবিষ্যৎ-দেখা নেই, ফি বাদ দিয়ে হিসাব। মন্টে কার্লো বলে ফলটা কতটা ভাগ্য। অতীতের ছবি, প্রতিশ্রুতি নয়।",
  },
};

const KIND_LABEL: Record<ProvKind, { en: string; bn: string }> = {
  vendor: { en: "external source", bn: "বাইরের উৎস" },
  engine: { en: "our quant engine · no AI", bn: "আমাদের ইঞ্জিন · AI নয়" },
  ai: { en: "AI model · evidence-locked", bn: "AI মডেল · প্রমাণে বাঁধা" },
};

export function kindLabel(kind: ProvKind): { en: string; bn: string } {
  return KIND_LABEL[kind];
}
