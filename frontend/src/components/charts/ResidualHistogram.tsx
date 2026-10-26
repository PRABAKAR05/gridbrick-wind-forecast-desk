/** Residual distribution with P10/P50/P90 markers. Computed client-side from the
 *  scatter payload so the user can flip between raw and decision-grade. */

import { useMemo, useState } from "react";
import type { AccuracyReport } from "@/api/types";
import { scaleLinear } from "@/lib/chart";
import { fmtInt, fmtSigned } from "@/lib/format";
import { Segmented } from "@/components/ui";
import { Axes, ChartTooltip, TooltipRow, useChartSize } from "./Shell";

const MARGIN = { top: 12, right: 14, bottom: 26, left: 44 };
const BINS = 34;

function quantile(sorted: number[], p: number): number {
  if (!sorted.length) return 0;
  const position = (sorted.length - 1) * p;
  const base = Math.floor(position);
  const rest = position - base;
  const lower = sorted[base] ?? 0;
  const upper = sorted[base + 1] ?? lower;
  return lower + rest * (upper - lower);
}

export function ResidualHistogram({
  scatter,
  height = 250,
}: {
  scatter: AccuracyReport["scatter"];
  height?: number;
}) {
  const { ref, width } = useChartSize();
  const [mode, setMode] = useState<"calibrated" | "raw">("calibrated");
  const [hover, setHover] = useState<number | null>(null);

  const inner = {
    left: MARGIN.left,
    top: MARGIN.top,
    width: Math.max(10, width - MARGIN.left - MARGIN.right),
    height: Math.max(10, height - MARGIN.top - MARGIN.bottom),
  };

  const model = useMemo(() => {
    const valued = scatter.filter((row) => row.calibrated !== null);
    const calibrated = valued.map((row) => (row.calibrated as number) - row.actual).sort((a, b) => a - b);
    const raw = scatter.map((row) => row.forecast - row.actual).sort((a, b) => a - b);
    const series = mode === "calibrated" ? calibrated : raw;
    const lo = Math.min(...raw, ...calibrated);
    const hi = Math.max(...raw, ...calibrated);
    const step = (hi - lo) / BINS || 1;
    const counts = new Array<number>(BINS).fill(0);
    for (const value of series) {
      const index = Math.min(BINS - 1, Math.max(0, Math.floor((value - lo) / step)));
      counts[index] = (counts[index] ?? 0) + 1;
    }
    const x = scaleLinear([lo, hi], [inner.left, inner.left + inner.width]);
    const maxCount = Math.max(...counts, 1);
    const y = scaleLinear([0, maxCount], [inner.top + inner.height, inner.top]);
    return {
      series,
      counts,
      step,
      lo,
      x,
      y,
      maxCount,
      p10: quantile(series, 0.1),
      p50: quantile(series, 0.5),
      p90: quantile(series, 0.9),
      mean: series.reduce((sum, value) => sum + value, 0) / (series.length || 1),
      n: series.length,
    };
  }, [scatter, mode, inner.left, inner.top, inner.width, inner.height]);

  const { x, y, counts, step, lo } = model;

  return (
    <div className="chart" ref={ref}>
      <div className="spread" style={{ marginBottom: 8 }}>
        <span className="legend small">
          Forecast minus outturn. Positive = the forecast ran high.
        </span>
        <Segmented
          ariaLabel="Residual basis"
          value={mode}
          onChange={setMode}
          options={[
            { value: "calibrated", label: "Decision-grade" },
            { value: "raw", label: "Raw" },
          ]}
        />
      </div>
      <svg
        width="100%"
        height={height}
        role="img"
        aria-label="Residual distribution"
        onMouseLeave={() => setHover(null)}
      >
        <Axes
          x={x}
          y={y}
          xTicks={[-4000, -2000, 0, 2000, 4000, 6000].filter((v) => v >= lo && v <= lo + step * BINS)}
          yTicks={[0, Math.round(model.maxCount / 2), model.maxCount]}
          inner={inner}
          xFormat={(value) => `${Math.round(value / 1000)}`}
          yFormat={(value) => value.toFixed(0)}
        />

        {counts.map((count, index) => {
          const left = x(lo + index * step);
          const right = x(lo + (index + 1) * step);
          return (
            <rect
              key={index}
              x={left}
              y={y(count)}
              width={Math.max(1, right - left - 1)}
              height={Math.max(0, inner.top + inner.height - y(count))}
              fill={hover === index ? "#FFC85C" : "rgba(255,176,32,0.55)"}
              rx={1}
              onMouseEnter={() => setHover(index)}
            />
          );
        })}

        <line x1={x(0)} x2={x(0)} y1={inner.top} y2={inner.top + inner.height} stroke="var(--line-3)" />
        {[
          { label: "P10", value: model.p10, color: "#5EA8FF" },
          { label: "P50", value: model.p50, color: "var(--text-2)" },
          { label: "P90", value: model.p90, color: "#FF6B6B" },
        ].map((marker) => (
          <g key={marker.label}>
            <line
              x1={x(marker.value)}
              x2={x(marker.value)}
              y1={inner.top}
              y2={inner.top + inner.height}
              stroke={marker.color}
              strokeDasharray="3 3"
              opacity={0.75}
            />
            <text
              x={x(marker.value)}
              y={inner.top + 9}
              textAnchor="middle"
              fill={marker.color}
              fontSize={8.5}
              className="mono"
            >
              {marker.label}
            </text>
          </g>
        ))}
      </svg>

      {hover !== null && (
        <ChartTooltip
          left={x(lo + (hover + 0.5) * step)}
          top={y(counts[hover] ?? 0) + 30}
          width={width}
        >
          <div className="tooltip__head">
            <span>
              {fmtSigned(lo + hover * step)} to {fmtSigned(lo + (hover + 1) * step)} MW
            </span>
          </div>
          <TooltipRow label="Observations" value={String(counts[hover] ?? 0)} />
          <TooltipRow label="Share" value={`${(((counts[hover] ?? 0) / model.n) * 100).toFixed(1)}%`} />
        </ChartTooltip>
      )}

      <div className="row small muted" style={{ justifyContent: "space-between", marginTop: 6 }}>
        <span>
          Mean {fmtSigned(model.mean)} MW · P10 {fmtInt(model.p10)} · P90 {fmtInt(model.p90)}
        </span>
        <span className="mono">{fmtInt(model.n)} hours</span>
      </div>
    </div>
  );
}
