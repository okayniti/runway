"use client";

import { motion } from "framer-motion";

const WIDTH = 800;
const HEIGHT = 320;
const PAD_X = 24;
const PAD_TOP = 28;
const PAD_BOTTOM = 44;

/** Catmull-Rom -> cubic Bezier conversion, so the line reads as a drawn
 * curve rather than a chart-library polyline, without pulling in a
 * charting dependency for 14 points. */
function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return "";
  const d: string[] = [`M ${points[0].x},${points[0].y}`];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d.push(`C ${c1x},${c1y} ${c2x},${c2y} ${p2.x},${p2.y}`);
  }
  return d.join(" ");
}

function formatCompact(value: number): string {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

export function ForecastChart({
  forecast,
  threshold,
  atRisk,
}: {
  forecast: number[];
  threshold: number;
  atRisk: boolean;
}) {
  const plotWidth = WIDTH - PAD_X * 2;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const dataMin = Math.min(...forecast);
  const dataMax = Math.max(...forecast);
  const dataRange = dataMax - dataMin || 1;

  // Only fold the threshold into the visible domain when it's reasonably
  // close to the forecast's own range -- otherwise a threshold set far
  // outside the forecast (or left at 0) would squash the real line flat.
  const thresholdIsNearby = threshold >= dataMin - dataRange && threshold <= dataMax + dataRange;
  const domainMin = thresholdIsNearby ? Math.min(dataMin, threshold) : dataMin;
  const domainMax = thresholdIsNearby ? Math.max(dataMax, threshold) : dataMax;
  const domainPad = (domainMax - domainMin || 1) * 0.15;
  const yMin = domainMin - domainPad;
  const yMax = domainMax + domainPad;

  const toX = (i: number) => PAD_X + (i / (forecast.length - 1)) * plotWidth;
  const toY = (v: number) => PAD_TOP + plotHeight - ((v - yMin) / (yMax - yMin)) * plotHeight;

  const points = forecast.map((v, i) => ({ x: toX(i), y: toY(v) }));
  const linePath = smoothPath(points);
  const areaPath = `${linePath} L ${points[points.length - 1].x},${PAD_TOP + plotHeight} L ${points[0].x},${PAD_TOP + plotHeight} Z`;

  const accent = atRisk ? "var(--color-ember)" : "var(--color-moss)";
  const gradientId = atRisk ? "forecastAreaEmber" : "forecastAreaMoss";

  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((t) => PAD_TOP + plotHeight * t);
  const dayTicks = [0, 3, 6, 9, 13];

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="14-day cash position forecast">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity={0.22} />
            <stop offset="100%" stopColor={accent} stopOpacity={0} />
          </linearGradient>
        </defs>

        {gridLines.map((y) => (
          <line key={y} x1={PAD_X} x2={WIDTH - PAD_X} y1={y} y2={y} stroke="var(--color-line)" strokeWidth={1} />
        ))}

        {thresholdIsNearby && (
          <>
            <line
              x1={PAD_X}
              x2={WIDTH - PAD_X}
              y1={toY(threshold)}
              y2={toY(threshold)}
              stroke="var(--color-ink-faint)"
              strokeWidth={1.5}
              strokeDasharray="5 5"
            />
            <text x={WIDTH - PAD_X} y={toY(threshold) - 8} textAnchor="end" className="fill-ink-faint text-[11px]">
              threshold {formatCompact(threshold)}
            </text>
          </>
        )}

        <motion.path
          d={areaPath}
          fill={`url(#${gradientId})`}
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.6, delay: 0.4 }}
        />

        <motion.path
          d={linePath}
          fill="none"
          stroke={accent}
          strokeWidth={3}
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          whileInView={{ pathLength: 1 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.1, ease: "easeInOut" }}
        />

        {points.map((p, i) => (
          <motion.circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={3.5}
            fill="var(--color-paper-card)"
            stroke={accent}
            strokeWidth={2}
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.3, delay: 0.5 + i * 0.04 }}
          />
        ))}

        {dayTicks.map((i) => (
          <text key={i} x={toX(i)} y={HEIGHT - 14} textAnchor="middle" className="fill-ink-muted text-[11px]">
            Day {i + 1}
          </text>
        ))}
      </svg>
    </div>
  );
}
