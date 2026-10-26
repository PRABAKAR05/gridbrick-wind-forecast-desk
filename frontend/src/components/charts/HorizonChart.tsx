/** Error growth with forecast horizon, with the day-ahead decision window marked. */

import { useMemo, useState } from "react";
import type { AccuracyReport } from "@/api/types";
import { niceDomain, path, scaleLinear, ticks } from "@/lib/chart";
import { fmtInt } from "@/lib/format";
import { Axes, ChartTooltip, DEFAULT_MARGIN, TooltipRow, useChartSize } from "./Shell";
import { Segmented } from "@/components/ui";

type MetricKey = "mae_mw" | "rmse_mw" | "mape_pct";

const LABELS: Record<MetricKey, string> = {
  mae_mw: "MAE (MW)",
  rmse_mw: "RMSE (MW)",
  mape_pct: "MAPE (%)",
};

export function HorizonChart({
  rows,
  height = 240,
}: {
  rows: AccuracyReport["by_horizon"];
  height?: number;
}) {
  const { ref, width } = useChartSize();
  const [metric, setMetric] = useState<MetricKey>("mae_mw");
  const [hover, setHover] = useState<number | null>(null);
  const margin = { ...DEFAULT_MARGIN, left: 48 };
  const inner = {
    left: margin.left,
    top: margin.top,
    width: Math.max(10, width - margin.left - margin.right),
    height: Math.max(10, height - margin.top - margin.bottom),
  };

  const { x, y, xTicks, yTicks } = useMemo(() => {
    const values = rows.map((row) => row[metric] ?? 0);
    const domain = niceDomain(0, Math.max(...values, 1), 0.08);
    const maxLead = Math.max(...rows.map((row) => row.lead_hours), 3);
    return {
      x: scaleLinear([0, maxLead + 3], [inner.left, inner.left + inner.width]),
      y: scaleLinear(domain, [inner.top + inner.height, inner.top]),
      xTicks: ticks(0, maxLead, 6),
      yTicks: ticks(domain[0], domain[1], 4),
    };
  }, [rows, metric, inner.left, inner.top, inner.width, inner.height]);

  const points = rows.map((row) => [x(row.lead_hours + 1.5), y(row[metric] ?? 0)] as const);

  const gateStart = x(14.5);
  const gateEnd = x(37.5);

  return (
    <div className="chart" ref={ref}>
      <div className="spread" style={{ marginBottom: 8 }}>
        <span className="legend small">Lead time = target hour minus publish time. Every stored vintage, not just the gate pick.</span>
        <Segmented
          ariaLabel="Horizon metric"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "mae_mw", label: "MAE" },
            { value: "rmse_mw", label: "RMSE" },
            { value: "mape_pct", label: "MAPE" },
          ]}
        />
      </div>
      <svg
        width="100%"
        height={height}
        role="img"
        aria-label="Forecast error by lead time"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const px = event.clientX - bounds.left;
          let closest = 0;
          let best = Number.POSITIVE_INFINITY;
          rows.forEach((row, index) => {
            const distance = Math.abs(x(row.lead_hours + 1.5) - px);
            if (distance < best) {
              best = distance;
              closest = index;
            }
          });
          setHover(closest);
        }}
      >
        <defs>
          <linearGradient id="horizon-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(255,176,32,0.28)" />
            <stop offset="100%" stopColor="rgba(255,176,32,0.01)" />
          </linearGradient>
        </defs>

        <rect
          x={gateStart}
          y={inner.top}
          width={Math.max(0, gateEnd - gateStart)}
          height={inner.height}
          fill="rgba(255,176,32,0.05)"
          stroke="rgba(255,176,32,0.18)"
          strokeDasharray="3 3"
        />
        <text className="chart__label" x={gateStart + 6} y={inner.top + 12}>
          DAY-AHEAD DECISION WINDOW
        </text>

        <Axes
          x={x}
          y={y}
          xTicks={xTicks}
          yTicks={yTicks}
          inner={inner}
          xFormat={(value) => `${value}h`}
          yFormat={(value) => (metric === "mape_pct" ? `${value.toFixed(0)}%` : value.toFixed(1))}
        />

        <path
          d={`${path(points)} L${points.at(-1)?.[0] ?? 0},${inner.top + inner.height} L${points[0]?.[0] ?? 0},${inner.top + inner.height} Z`}
          fill="url(#horizon-fill)"
        />
        <path d={path(points)} fill="none" stroke="#FFB020" strokeWidth={2} />

        {hover !== null && rows[hover] && (
          <g pointerEvents="none">
            <line
              x1={x(rows[hover]!.lead_hours + 1.5)}
              x2={x(rows[hover]!.lead_hours + 1.5)}
              y1={inner.top}
              y2={inner.top + inner.height}
              stroke="var(--line-3)"
              strokeDasharray="2 3"
            />
            <circle
              cx={x(rows[hover]!.lead_hours + 1.5)}
              cy={y(rows[hover]![metric] ?? 0)}
              r={3.5}
              fill="#0B0D10"
              stroke="#FFB020"
              strokeWidth={2}
            />
          </g>
        )}
      </svg>

      {hover !== null && rows[hover] && (
        <ChartTooltip left={x(rows[hover]!.lead_hours + 1.5)} top={inner.top + 12} width={width}>
          <div className="tooltip__head">
            <span>{rows[hover]!.lead_label}</span>
            <span>{fmtInt(rows[hover]!.n)} obs</span>
          </div>
          <TooltipRow color="#FFB020" label="MAE" value={`${fmtInt(rows[hover]!.mae_mw)} MW`} />
          <TooltipRow label="RMSE" value={`${fmtInt(rows[hover]!.rmse_mw)} MW`} />
          <TooltipRow label="Bias" value={`${fmtInt(rows[hover]!.bias_mw)} MW`} />
          <TooltipRow label={LABELS[metric]} value={metric === "mape_pct" ? `${(rows[hover]!.mape_pct ?? 0).toFixed(1)}%` : fmtInt(rows[hover]![metric] as number)} />
        </ChartTooltip>
      )}
    </div>
  );
}
