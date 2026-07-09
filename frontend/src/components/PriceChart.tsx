"use client";

/** DARKPOOL candle chart — lightweight-charts v5.
 *  Candles + EMA(20/50) trend lines + a volume histogram + liquidity price
 *  lines (PDH/PDL/PWH/PWL amber, EQH/EQL cyan) + the last structure event as a
 *  marker. Everything here is deterministic engine/exchange data — no gold, no
 *  AI. Zone rectangles (OB/FVG) arrive with the P2 overlay canvas; for now
 *  zones live in the rail list.
 *  Glow discipline: the container carries the ambient live-data glow; chart
 *  chrome itself stays flat. */

import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Kline, LevelOut, StructureEvent } from "@/lib/api";

const C = {
  bull: "#2dd4bf",
  bear: "#f87171",
  warn: "#f5b94a",
  pulse: "#7dd3fc",
  dim: "#5a6778",
  hair: "#0f1520",
  text: "#93a0b4",
  ema20: "#c2cbd9",
  ema50: "#7c8698",
};

function toTime(iso: string): UTCTimestamp {
  return Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;
}

/** EMA over a numeric series, seeded with an SMA; null until the period fills. */
function ema(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) {
      out.push(null);
      continue;
    }
    if (prev === null) {
      let s = 0;
      for (let j = i - period + 1; j <= i; j++) s += values[j];
      prev = s / period;
    } else {
      prev = values[i] * k + prev * (1 - k);
    }
    out.push(prev);
  }
  return out;
}

export default function PriceChart({
  candles,
  levels,
  lastEvent,
  liveTick,
}: {
  candles: Kline[];
  levels: LevelOut[];
  lastEvent: StructureEvent | null;
  /** Latest WS tick for the currently-forming bar (P3) — cheap `.update()`
   *  path, separate from the full `setData()` reload above. A bar rollover
   *  is the caller's job (append it into `candles` instead), so this effect
   *  can assume `liveTick` always updates the SAME last bar. */
  liveTick?: Kline | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const fittedRef = useRef(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: C.text,
        fontFamily: "var(--font-geist-mono), monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: C.hair },
        horzLines: { color: C.hair },
      },
      rightPriceScale: { borderColor: C.hair, scaleMargins: { top: 0.06, bottom: 0.26 } },
      timeScale: { borderColor: C.hair, timeVisible: true, secondsVisible: false },
      crosshair: {
        horzLine: { color: C.dim, labelBackgroundColor: "#131a23" },
        vertLine: { color: C.dim, labelBackgroundColor: "#131a23" },
      },
    });

    // Volume — its own overlay scale, pinned to the bottom ~20% band.
    const vol = chart.addSeries(HistogramSeries, {
      priceScaleId: "vol",
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    // EMA trend lines — neutral (data), thin, no axis clutter.
    const mkLine = (color: string) =>
      chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    const ema20Series = mkLine(C.ema20);
    const ema50Series = mkLine(C.ema50);

    const series = chart.addSeries(CandlestickSeries, {
      upColor: C.bull,
      downColor: C.bear,
      wickUpColor: C.bull,
      wickDownColor: C.bear,
      borderVisible: false,
    });

    chartRef.current = chart;
    seriesRef.current = series;
    ema20Ref.current = ema20Series;
    ema50Ref.current = ema50Series;
    volRef.current = vol;
    markersRef.current = createSeriesMarkers(series, []);

    const resize = () => chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(el);

    return () => {
      observer.disconnect();
      markersRef.current = null;
      seriesRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      volRef.current = null;
      chartRef.current = null;
      chart.remove();
    };
  }, []);

  // Data + decorations (reruns on each poll; chart object persists).
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    series.setData(
      candles.map((k) => ({
        time: toTime(k.open_time),
        open: parseFloat(k.open),
        high: parseFloat(k.high),
        low: parseFloat(k.low),
        close: parseFloat(k.close),
      })),
    );

    // EMA lines + volume histogram (parseFloat only at this display boundary).
    const closes = candles.map((k) => parseFloat(k.close));
    const times = candles.map((k) => toTime(k.open_time));
    const line = (period: number) =>
      ema(closes, period)
        .map((v, i) => (v === null ? null : { time: times[i], value: v }))
        .filter((p): p is { time: UTCTimestamp; value: number } => p !== null);
    ema20Ref.current?.setData(line(20));
    ema50Ref.current?.setData(line(50));
    volRef.current?.setData(
      candles.map((k) => {
        const up = parseFloat(k.close) >= parseFloat(k.open);
        return {
          time: toTime(k.open_time),
          value: parseFloat(k.volume),
          color: up ? "rgba(45,212,191,0.32)" : "rgba(248,113,113,0.32)",
        };
      }),
    );

    if (!fittedRef.current && candles.length > 0) {
      chartRef.current?.timeScale().fitContent();
      fittedRef.current = true;
    }

    for (const l of priceLinesRef.current) series.removePriceLine(l);
    priceLinesRef.current = levels
      .filter((lv) => lv.state !== "broken")
      .map((lv) =>
        series.createPriceLine({
          price: parseFloat(lv.price),
          color: lv.kind.startsWith("EQ")
            ? lv.state === "swept" ? C.dim : C.pulse
            : lv.state === "swept" ? C.dim : C.warn,
          lineWidth: 1,
          lineStyle: lv.state === "swept" ? LineStyle.Dotted : LineStyle.Dashed,
          axisLabelVisible: true,
          title: lv.kind + (lv.state === "swept" ? " (swept)" : ""),
        }),
      );

    const markers: SeriesMarker<Time>[] = [];
    if (lastEvent && candles.length > 0) {
      const t = toTime(lastEvent.time);
      const inRange = t >= toTime(candles[0].open_time) && t <= toTime(candles[candles.length - 1].open_time);
      if (inRange) {
        markers.push({
          time: t,
          position: lastEvent.direction === "bullish" ? "belowBar" : "aboveBar",
          shape: lastEvent.direction === "bullish" ? "arrowUp" : "arrowDown",
          color: lastEvent.direction === "bullish" ? C.bull : C.bear,
          text: lastEvent.kind,
        });
      }
    }
    markersRef.current?.setMarkers(markers);
  }, [candles, levels, lastEvent]);

  // Live tick (P3) — cheap `.update()` of just the forming bar, not a full
  // `setData()` reload. Recomputing EMA over ~200-300 closes on every tick is
  // trivial CPU work (sub-millisecond); what's expensive is reflowing the
  // WHOLE series in the chart library, which this avoids by updating only
  // the last point of each series.
  useEffect(() => {
    if (!liveTick || candles.length === 0) return;
    const series = seriesRef.current;
    if (!series) return;

    const time = toTime(liveTick.open_time);
    series.update({
      time,
      open: parseFloat(liveTick.open),
      high: parseFloat(liveTick.high),
      low: parseFloat(liveTick.low),
      close: parseFloat(liveTick.close),
    });

    const working = [...candles.slice(0, -1), liveTick];
    const closes = working.map((k) => parseFloat(k.close));
    const last20 = ema(closes, 20).at(-1);
    const last50 = ema(closes, 50).at(-1);
    if (last20 !== null && last20 !== undefined) ema20Ref.current?.update({ time, value: last20 });
    if (last50 !== null && last50 !== undefined) ema50Ref.current?.update({ time, value: last50 });

    const up = parseFloat(liveTick.close) >= parseFloat(liveTick.open);
    volRef.current?.update({
      time,
      value: parseFloat(liveTick.volume),
      color: up ? "rgba(45,212,191,0.32)" : "rgba(248,113,113,0.32)",
    });
  }, [liveTick]);

  // absolute inset-0 (parent is position:relative): the mount always gets real
  // pixels — a percentage-height chain through nested flex can silently give 0.
  return (
    <>
      <div ref={containerRef} className="absolute inset-0" />
      <div className="pointer-events-none absolute top-2 left-3 z-10 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[9px] text-dim">
        <span className="flex items-center gap-1">
          <span className="inline-block h-[2px] w-3.5 rounded-full" style={{ background: C.ema20 }} />
          EMA20
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-[2px] w-3.5 rounded-full" style={{ background: C.ema50 }} />
          EMA50
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-1.5 rounded-[1px]" style={{ background: "rgba(45,212,191,0.4)" }} />
          VOL
        </span>
      </div>
    </>
  );
}
