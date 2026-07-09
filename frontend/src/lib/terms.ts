/** Maps engine enum values → glossary keys, so the words the desk prints
 *  (a trend, a direction, an alignment bias) are themselves hoverable and
 *  explained in Bengali. Keeps <Term> call sites terse. */

import type { GlossaryKey } from "@/lib/glossary";

export function trendKey(trend: string): GlossaryKey {
  return trend === "bullish" ? "BULLISH" : trend === "bearish" ? "BEARISH" : "RANGE";
}

export function dirKey(dir: string): GlossaryKey {
  return dir === "long" ? "LONG" : dir === "short" ? "SHORT" : dir === "no_trade" ? "NO_TRADE" : "NEUTRAL";
}

export function biasKey(bias: string): GlossaryKey {
  return bias === "long" ? "LONG_BIAS" : bias === "short" ? "SHORT_BIAS" : "MIXED";
}
