/** Reliability diagram: does an 80% band actually contain 80% of outcomes? */

import { useState } from "react";
import type { AccuracyReport } from "@/api/types";
import { path, scaleLinear } from "@/lib/chart";
import { fmtFractionPct } from "@/lib/format";
import { Axes, ChartTooltip, TooltipRow, useChartSize } from "./Shell";

const MARGIN = { top: 12, right: 16, bottom: 26, left: 42 };

export function CalibrationChart({
  table,
  height = 250,
}: {
  table: AccuracyReport["calibration"]["walk_forward"]["table"];
  height?: number;
}) {
  const { ref, width } = useChartSize();
  const [hover, setHover] = useState<number | null>(null);
  const inner = {
    left: MARGIN.left,
    top: MARGIN.top,
    width: Math.max(10, width - MARGIN.left - MARGIN.right),
    height: Math.max(10, height - MARGIN.top - MARGIN.bottom),
  };

  const min = Math.min(...table.map((row) => row.nominal)) - 0.05;
  const max = Math.max(...table.map((row) => row.nominal)) + 0.03;
  const x = scaleLinear([min, max], [inner.left, inner.left + inner.width]);
  const y = scaleLinear([0, 1], [inner.top + inner.height, inner.top]);

  const inflated = table
    .filter((row) => row.observed !== null)
    .map((row) => [x(row.nominal), y(row.observed as number)] as const);
  const raw = table
    .filter((row) => row.raw_observed !== null)
    .map((row) => [x(row.nominal), y(row.raw_observed as number)] as const);

  const xTicks = table.map((row) => row.nominal);

  return (
    <div className="chart" ref={ref}>
      <svg
        width="100%"
        height={height}
        role="img"
        aria-label="Reliability diagram of predictive intervals"
        onMouseLeave={() => setHover(null)}
      >
        <Axes
          x={x}
          y={y}
          xTicks={xTicks}
          yTicks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
          inner={inner}
          xFormat={(value) => `${Math.round(value * 100)}%`}
          yFormat={(value) => `${Math.round(value * 100)}%`}
          showXGrid
        />

        <line
          x1={x(min)}
          y1={y(min)}
          x2={x(max)}
          y2={y(max)}
          stroke="var(--line-3)"
          strokeDasharray="4 4"
        />
        <text className="chart__label" x={x(max) - 96} y={y(max) + 16}>
          PERFECT CALIBRATION
        </text>

        <path d={path(raw)} fill="none" stroke="#6B7686" strokeWidth={1.6} strokeDasharray="4 3" />
        <path d={path(inflated)} fill="none" stroke="#FFB020" strokeWidth={2.1} strokeLinecap="round" />

        {table.map((row, index) => (
          <g key={row.nominal}>
            <circle
              cx={x(row.nominal)}
              cy={y(row.observed ?? 0)}
              r={hover === index ? 4.5 : 3}
              fill="#0B0D10"
              stroke="#FFB020"
              strokeWidth={2}
            />
            <rect
              x={x(row.nominal) - 14}
              y={inner.top}
              width={28}
              height={inner.height}
              fill="transparent"
              onMouseEnter={() => setHover(index)}
            />
          </g>
        ))}
      </svg>

      {hover !== null && table[hover] && (
        <ChartTooltip left={x(table[hover]!.nominal)} top={inner.top + 10} width={width}>
          <div className="tooltip__head">
            <span>Nominal {fmtFractionPct(table[hover]!.nominal, 0)}</span>
            <span>{table[hover]!.samples} obs</span>
          </div>
          <TooltipRow color="#FFB020" label="Delivered band" value={fmtFractionPct(table[hover]!.observed)} />
          <TooltipRow color="#6B7686" label="Un-inflated" value={fmtFractionPct(table[hover]!.raw_observed)} />
          <TooltipRow
            label="Gap"
            value={
              <span className={(table[hover]!.gap ?? 0) >= 0 ? "t-pos" : "t-neg"}>
                {fmtFractionPct(table[hover]!.gap)}
              </span>
            }
          />
        </ChartTooltip>
      )}
    </div>
  );
}
