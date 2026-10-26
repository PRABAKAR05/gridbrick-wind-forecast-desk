/** Thermal procurement: the volume a desk would buy on the raw forecast vs the
 *  volume it buys once wind uncertainty is priced. The shaded wedge is the
 *  risk premium, in MW, hour by hour. */

import { useMemo, useState } from "react";
import type { PlanHour } from "@/api/types";
import { bandPath, niceDomain, path, scaleLinear, ticks } from "@/lib/chart";
import { fmtInt, hourLabel } from "@/lib/format";
import { Legend } from "@/components/ui";
import { Axes, ChartTooltip, DEFAULT_MARGIN, TooltipRow, useChartSize } from "./Shell";

const COLORS = {
  procured: "#FFB020",
  baseline: "#7C8798",
  demand: "#5EA8FF",
  uplift: "rgba(255,176,32,0.16)",
};

export function ThermalChart({ hours, height = 280 }: { hours: PlanHour[]; height?: number }) {
  const { ref, width } = useChartSize();
  const [hover, setHover] = useState<number | null>(null);
  const [layers, setLayers] = useState({ demand: true, baseline: true });

  const margin = DEFAULT_MARGIN;
  const inner = {
    left: margin.left,
    top: margin.top,
    width: Math.max(10, width - margin.left - margin.right),
    height: Math.max(10, height - margin.top - margin.bottom),
  };

  const model = useMemo(() => {
    const count = hours.length;
    const x = (index: number) => inner.left + (count <= 1 ? 0 : (index / (count - 1)) * inner.width);
    const values: number[] = [];
    for (const row of hours) {
      for (const value of [row.demand_mw, row.thermal_baseline_mw, row.thermal_procured_mw]) {
        if (value !== null && value !== undefined) values.push(value);
      }
    }
    const domain = niceDomain(
      values.length ? Math.min(...values) : 0,
      values.length ? Math.max(...values) : 1,
      0.08,
    );
    const y = scaleLinear(domain, [inner.top + inner.height, inner.top]);
    return { x, y, domain, count };
  }, [hours, inner.left, inner.top, inner.width, inner.height]);

  const { x, y } = model;

  const line = (key: "demand_mw" | "thermal_baseline_mw" | "thermal_procured_mw") =>
    path(
      hours
        .map((row, index) => {
          const value = row[key];
          return value === null || value === undefined ? null : ([x(index), y(value)] as const);
        })
        .filter((point): point is readonly [number, number] => point !== null),
    );

  const upper = hours.map(
    (row, index) => [x(index), y(row.thermal_procured_mw ?? row.thermal_baseline_mw ?? 0)] as const,
  );
  const lower = hours.map(
    (row, index) => [x(index), y(row.thermal_baseline_mw ?? row.thermal_procured_mw ?? 0)] as const,
  );

  const xTicks = hours.filter((_, index) => index % 3 === 0).map((_, index) => index * 3);
  const yTicks = ticks(model.domain[0], model.domain[1], 5);
  const hovered = hover !== null ? hours[hover] : undefined;

  return (
    <div className="chart" ref={ref}>
      <Legend
        items={[
          { label: "Thermal procured (risk-adjusted)", color: COLORS.procured },
          {
            label: "Nominal thermal",
            color: COLORS.baseline,
            kind: "dash",
            off: !layers.baseline,
            onClick: () => setLayers((s) => ({ ...s, baseline: !s.baseline })),
          },
          {
            label: "Demand input",
            color: COLORS.demand,
            off: !layers.demand,
            onClick: () => setLayers((s) => ({ ...s, demand: !s.demand })),
          },
          { label: "Risk uplift", color: "rgba(255,176,32,0.4)", kind: "area" },
        ]}
      />
      <div style={{ height: 10 }} />
      <svg
        width="100%"
        height={height}
        role="img"
        aria-label="Thermal procurement against demand and nominal baseline"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - bounds.left - inner.left) / Math.max(1, inner.width);
          const index = Math.round(ratio * (hours.length - 1));
          setHover(Math.max(0, Math.min(hours.length - 1, index)));
        }}
      >
        <Axes
          x={x}
          y={y}
          xTicks={xTicks}
          yTicks={yTicks}
          inner={inner}
          xFormat={(value) => hourLabel(value)}
          yFormat={(value) => (value / 1000).toFixed(0)}
          yLabel="GW"
        />

        {layers.baseline && (
          <path d={bandPath(upper, lower)} fill={COLORS.uplift} stroke="none" />
        )}

        {layers.demand && (
          <path
            d={line("demand_mw")}
            fill="none"
            stroke={COLORS.demand}
            strokeWidth={1.4}
            strokeDasharray="5 4"
            opacity={0.8}
          />
        )}

        {layers.baseline && (
          <path
            d={line("thermal_baseline_mw")}
            fill="none"
            stroke={COLORS.baseline}
            strokeWidth={1.5}
            strokeDasharray="3 3"
          />
        )}

        <path
          d={line("thermal_procured_mw")}
          fill="none"
          stroke={COLORS.procured}
          strokeWidth={2.1}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {hover !== null && hovered && (
          <g pointerEvents="none">
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={inner.top}
              y2={inner.top + inner.height}
              stroke="var(--line-3)"
              strokeDasharray="2 3"
            />
            {hovered.thermal_procured_mw !== null && (
              <circle
                cx={x(hover)}
                cy={y(hovered.thermal_procured_mw)}
                r={3.5}
                fill="#0B0D10"
                stroke={COLORS.procured}
                strokeWidth={2}
              />
            )}
          </g>
        )}
      </svg>

      {hover !== null && hovered && (
        <ChartTooltip left={x(hover)} top={inner.top + 8} width={width}>
          <div className="tooltip__head">
            <span>{hourLabel(hovered.hour)}</span>
            <span>{fmtInt(hovered.uplift_mw)} MW uplift</span>
          </div>
          <TooltipRow color={COLORS.demand} label="Demand" value={`${fmtInt(hovered.demand_mw)} MW`} />
          <TooltipRow
            color={COLORS.procured}
            label="Wind nominated"
            value={`${fmtInt(hovered.wind_nominated_mw)} MW`}
          />
          <TooltipRow label="Nominal thermal" value={`${fmtInt(hovered.thermal_baseline_mw)} MW`} />
          <TooltipRow label="Procured thermal" value={`${fmtInt(hovered.thermal_procured_mw)} MW`} />
        </ChartTooltip>
      )}
    </div>
  );
}
