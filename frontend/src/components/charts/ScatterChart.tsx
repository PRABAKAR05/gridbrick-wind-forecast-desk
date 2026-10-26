/** Forecast vs outturn scatter, with the 45-degree reference. Tightening the
 *  cloud around y=x is the visual proof that recalibration works. */

import { useMemo, useState } from "react";
import type { AccuracyReport } from "@/api/types";
import { niceDomain, scaleLinear, ticks } from "@/lib/chart";
import { fmtInt } from "@/lib/format";
import { Segmented } from "@/components/ui";
import { Axes, ChartTooltip, TooltipRow, useChartSize } from "./Shell";

const MARGIN = { top: 12, right: 14, bottom: 26, left: 46 };

export function ScatterChart({
  scatter,
  height = 288,
}: {
  scatter: AccuracyReport["scatter"];
  height?: number;
}) {
  const { ref, width } = useChartSize();
  const [mode, setMode] = useState<"calibrated" | "raw">("calibrated");
  const [hover, setHover] = useState<{ x: number; y: number; label: string } | null>(null);

  const inner = {
    left: MARGIN.left,
    top: MARGIN.top,
    width: Math.max(10, width - MARGIN.left - MARGIN.right),
    height: Math.max(10, height - MARGIN.top - MARGIN.bottom),
  };

  const { x, y, domain } = useMemo(() => {
    const xs = scatter.map((row) => (mode === "calibrated" ? (row.calibrated ?? row.forecast) : row.forecast));
    const ys = scatter.map((row) => row.actual);
    const max = Math.max(...xs, ...ys, 1);
    const dom = niceDomain(0, max, 0.02);
    return {
      x: scaleLinear(dom, [inner.left, inner.left + inner.width]),
      y: scaleLinear(dom, [inner.top + inner.height, inner.top]),
      domain: dom,
    };
  }, [scatter, mode, inner.left, inner.top, inner.width, inner.height]);

  const labels = ticks(domain[0] / 1000, domain[1] / 1000, 4);

  return (
    <div className="chart" ref={ref}>
      <div className="spread" style={{ marginBottom: 8 }}>
        <span className="legend small">Each dot is one delivery hour. The ideal is a thin cloud on the diagonal.</span>
        <Segmented
          ariaLabel="Scatter basis"
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
        aria-label="Forecast versus outturn scatter"
        onMouseLeave={() => setHover(null)}
      >
        <Axes
          x={x}
          y={y}
          xTicks={labels.map((v) => v * 1000)}
          yTicks={labels.map((v) => v * 1000)}
          inner={inner}
          xFormat={(value) => (value / 1000).toFixed(0)}
          yFormat={(value) => (value / 1000).toFixed(0)}
          showXGrid
          yLabel="ACTUAL GW"
        />

        <line
          x1={x(domain[0])}
          y1={y(domain[0])}
          x2={x(domain[1])}
          y2={y(domain[1])}
          stroke="var(--line-3)"
          strokeDasharray="4 4"
        />

        {scatter.map((row, index) => {
          const forecast = mode === "calibrated" ? (row.calibrated ?? row.forecast) : row.forecast;
          return (
            <circle
              key={index}
              cx={x(forecast)}
              cy={y(row.actual)}
              r={2.1}
              fill={mode === "calibrated" ? "rgba(255,176,32,0.62)" : "rgba(124,135,152,0.5)"}
              onMouseEnter={() => setHover({ x: forecast, y: row.actual, label: `${fmtInt(forecast)} → ${fmtInt(row.actual)}` })}
            />
          );
        })}
      </svg>

      {hover && (
        <ChartTooltip left={x(hover.x)} top={y(hover.y)} width={width}>
          <div className="tooltip__head">
            <span>Forecast → outturn</span>
          </div>
          <TooltipRow label="MW" value={hover.label} />
          <TooltipRow
            label="Error"
            value={
              <span className={hover.x - hover.y > 0 ? "t-neg" : "t-pos"}>
                {fmtInt(hover.x - hover.y)} MW
              </span>
            }
          />
        </ChartTooltip>
      )}
    </div>
  );
}
