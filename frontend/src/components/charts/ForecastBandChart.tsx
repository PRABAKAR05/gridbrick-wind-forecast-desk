/** The Decision Desk centrepiece: a day-ahead wind forecast with its empirical
 *  predictive band, the raw feed for reference, and the outturn once known. */

import { useMemo, useState } from "react";
import type { DecisionHour } from "@/api/types";
import { bandPath, niceDomain, path, scaleLinear, ticks } from "@/lib/chart";
import { fmtInt, fmtSigned, hourLabel } from "@/lib/format";
import { Axes, ChartTooltip, DEFAULT_MARGIN, TooltipRow, useChartSize } from "./Shell";
import { Legend } from "@/components/ui";

interface Props {
  hours: DecisionHour[];
  height?: number;
  realised: boolean;
}

const COLORS = {
  actual: "#5EA8FF",
  calibrated: "#FFB020",
  raw: "#7C8798",
  band: "rgba(255,176,32,0.10)",
  bandInner: "rgba(255,176,32,0.18)",
};

export function ForecastBandChart({ hours, height = 300, realised }: Props) {
  const { ref, width } = useChartSize();
  const [hover, setHover] = useState<number | null>(null);
  const [layers, setLayers] = useState({ raw: true, actual: true, band: true });

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
      for (const value of [row.forecast_mw, row.calibrated_mw, row.actual_mw, row.band?.p10, row.band?.p90]) {
        if (value !== null && value !== undefined && Number.isFinite(value)) values.push(value);
      }
    }
    const domain = niceDomain(
      values.length ? Math.min(...values) : 0,
      values.length ? Math.max(...values) : 1,
      0.1,
    );
    const y = scaleLinear(domain, [inner.top + inner.height, inner.top]);
    return { x, y, count, domain };
  }, [hours, inner.left, inner.top, inner.width, inner.height]);

  const { x, y } = model;
  const hasBand = hours.some((row) => row.band);
  const hasActual = realised && hours.some((row) => row.actual_mw !== null);

  const outerUpper = hours.map((row, index) => [x(index), y(row.band?.p90 ?? row.calibrated_mw ?? 0)] as const);
  const outerLower = hours.map((row, index) => [x(index), y(row.band?.p10 ?? row.calibrated_mw ?? 0)] as const);
  const innerUpper = hours.map((row, index) => [x(index), y(row.band?.p75 ?? row.calibrated_mw ?? 0)] as const);
  const innerLower = hours.map((row, index) => [x(index), y(row.band?.p25 ?? row.calibrated_mw ?? 0)] as const);

  const line = (key: "forecast_mw" | "calibrated_mw" | "actual_mw") =>
    path(
      hours
        .map((row, index) => {
          const value = row[key];
          return value === null || value === undefined
            ? null
            : ([x(index), y(value)] as const);
        })
        .filter((point): point is readonly [number, number] => point !== null),
    );

  const xTicks = hours.filter((_, index) => index % 3 === 0).map((_, index) => index * 3).filter((v) => v < hours.length);
  const yTicks = ticks(model.domain[0], model.domain[1], 5);

  const hovered = hover !== null ? hours[hover] : undefined;

  return (
    <div className="chart" ref={ref}>
      <Legend
        items={[
          {
            label: "Decision-grade (calibrated)",
            color: COLORS.calibrated,
            off: false,
          },
          { label: "Raw Elexon WINDFOR", color: COLORS.raw, kind: "dash", off: !layers.raw, onClick: () => setLayers((s) => ({ ...s, raw: !s.raw })) },
          { label: "Outturn", color: COLORS.actual, kind: "dash", off: !layers.actual || !hasActual, onClick: () => setLayers((s) => ({ ...s, actual: !s.actual })) },
          { label: "P10–P90 predictive band", color: "rgba(255,176,32,0.32)", kind: "area", off: !layers.band, onClick: () => setLayers((s) => ({ ...s, band: !s.band })) },
        ]}
      />
      <div style={{ height: 10 }} />
      <svg
        width="100%"
        height={height}
        role="img"
        aria-label="Hourly wind forecast with predictive band and outturn"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const offset = event.clientX - bounds.left;
          const ratio = (offset - inner.left) / Math.max(1, inner.width);
          const index = Math.round(ratio * (hours.length - 1));
          setHover(Math.max(0, Math.min(hours.length - 1, index)));
        }}
      >
        <defs>
          <linearGradient id="forecast-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#FFB020" />
            <stop offset="100%" stopColor="#FFD37A" />
          </linearGradient>
        </defs>

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

        {layers.band && hasBand && (
          <>
            <path d={bandPath(outerUpper, outerLower)} fill={COLORS.band} stroke="none" />
            <path d={bandPath(innerUpper, innerLower)} fill={COLORS.bandInner} stroke="none" />
            <path
              d={path(outerUpper)}
              fill="none"
              stroke="rgba(255,176,32,0.28)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <path
              d={path(outerLower)}
              fill="none"
              stroke="rgba(255,176,32,0.28)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
          </>
        )}

        {layers.raw && (
          <path d={line("forecast_mw")} fill="none" stroke={COLORS.raw} strokeWidth={1.25} strokeDasharray="4 3" opacity={0.85} />
        )}

        <path
          d={line("calibrated_mw")}
          fill="none"
          stroke="url(#forecast-line)"
          strokeWidth={2.1}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {layers.actual && hasActual && (
          <path
            d={line("actual_mw")}
            fill="none"
            stroke={COLORS.actual}
            strokeWidth={1.9}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

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
            {hovered.calibrated_mw !== null && (
              <circle cx={x(hover)} cy={y(hovered.calibrated_mw)} r={3.5} fill="#0B0D10" stroke={COLORS.calibrated} strokeWidth={2} />
            )}
            {hovered.actual_mw !== null && layers.actual && (
              <circle cx={x(hover)} cy={y(hovered.actual_mw)} r={3.5} fill="#0B0D10" stroke={COLORS.actual} strokeWidth={2} />
            )}
          </g>
        )}
      </svg>

      {hover !== null && hovered && (
        <ChartTooltip left={x(hover)} top={inner.top + 8} width={width}>
          <div className="tooltip__head">
            <span>{hourLabel(hovered.hour)}</span>
            <span>{hovered.lead_hours !== null ? `${hovered.lead_hours.toFixed(1)}h lead` : ""}</span>
          </div>
          <TooltipRow color={COLORS.calibrated} label="Decision-grade" value={`${fmtInt(hovered.calibrated_mw)} MW`} />
          <TooltipRow color={COLORS.raw} label="Raw forecast" value={`${fmtInt(hovered.forecast_mw)} MW`} />
          {hovered.band && (
            <TooltipRow
              label="P10 – P90"
              value={`${fmtInt(hovered.band.p10)} – ${fmtInt(hovered.band.p90)}`}
            />
          )}
          {hovered.actual_mw !== null && (
            <TooltipRow color={COLORS.actual} label="Outturn" value={`${fmtInt(hovered.actual_mw)} MW`} />
          )}
          {hovered.residual_mw !== null && (
            <TooltipRow
              label="Error"
              value={<span className={hovered.residual_mw > 0 ? "t-neg" : "t-pos"}>{fmtSigned(hovered.residual_mw)} MW</span>}
            />
          )}
        </ChartTooltip>
      )}
    </div>
  );
}
