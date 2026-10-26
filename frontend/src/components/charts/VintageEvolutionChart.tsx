/** How the forecast for a delivery day was revised across vintages, up to gate. */

import { useMemo, useState } from "react";
import type { VintageEvolution } from "@/api/types";
import { niceDomain, path, scaleLinear, ticks } from "@/lib/chart";
import { fmtInt, fmtTime, hourLabel } from "@/lib/format";
import { Axes, ChartTooltip, DEFAULT_MARGIN, TooltipRow, useChartSize } from "./Shell";

export function VintageEvolutionChart({
  data,
  height = 210,
}: {
  data: VintageEvolution;
  height?: number;
}) {
  const { ref, width } = useChartSize();
  const [hover, setHover] = useState<number | null>(null);
  const margin = { ...DEFAULT_MARGIN, left: 44, top: 10 };
  const inner = {
    left: margin.left,
    top: margin.top,
    width: Math.max(10, width - margin.left - margin.right),
    height: Math.max(10, height - margin.top - margin.bottom),
  };

  const count = data.vintages.length;

  const { x, y, domain } = useMemo(() => {
    const values: number[] = [];
    for (const series of data.vintages) {
      for (const value of series.values) if (value !== null && Number.isFinite(value)) values.push(value);
    }
    for (const value of data.actual_mw ?? []) if (value !== null && Number.isFinite(value)) values.push(value);
    const dom = niceDomain(
      values.length ? Math.min(...values) : 0,
      values.length ? Math.max(...values) : 1,
      0.12,
    );
    return {
      x: (index: number) => inner.left + (24 <= 1 ? 0 : (index / 23) * inner.width),
      y: scaleLinear(dom, [inner.top + inner.height, inner.top]),
      domain: dom,
    };
  }, [data, inner.left, inner.top, inner.width, inner.height]);

  const xTicks = [0, 6, 12, 18, 23];
  const yTicks = ticks(domain[0], domain[1], 4);

  return (
    <div className="chart" ref={ref}>
      <svg
        width="100%"
        height={height}
        role="img"
        aria-label="Forecast revisions across vintages"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - bounds.left - inner.left) / Math.max(1, inner.width);
          setHover(Math.max(0, Math.min(23, Math.round(ratio * 23))));
        }}
      >
        <Axes
          x={x}
          y={y}
          xTicks={xTicks}
          yTicks={yTicks}
          inner={inner}
          xFormat={hourLabel}
          yFormat={(value) => (value / 1000).toFixed(0)}
          yLabel="GW"
        />

        {data.vintages.map((series, seriesIndex) => {
          const isSelected = series.publish_time_utc === data.selected_vintage_utc;
          const age = count <= 1 ? 1 : seriesIndex / (count - 1);
          const d = path(
            series.values
              .map((value, index) =>
                value === null ? null : ([x(index), y(value)] as const),
              )
              .filter((point): point is readonly [number, number] => point !== null),
          );
          return (
            <path
              key={series.publish_time_utc}
              d={d}
              fill="none"
              stroke={isSelected ? "#FFB020" : "#6B7686"}
              strokeWidth={isSelected ? 2 : 1}
              strokeOpacity={isSelected ? 1 : 0.16 + age * 0.5}
              strokeLinecap="round"
            />
          );
        })}

        {data.actual_mw && (
          <path
            d={path(
              data.actual_mw
                .map((value, index) => (value === null ? null : ([x(index), y(value)] as const)))
                .filter((point): point is readonly [number, number] => point !== null),
            )}
            fill="none"
            stroke="#5EA8FF"
            strokeWidth={1.7}
            strokeDasharray="5 3"
          />
        )}

        {hover !== null && (
          <g pointerEvents="none">
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={inner.top}
              y2={inner.top + inner.height}
              stroke="var(--line-3)"
              strokeDasharray="2 3"
            />
          </g>
        )}
      </svg>

      {hover !== null && (
        <ChartTooltip left={x(hover)} top={inner.top + 6} width={width}>
          <div className="tooltip__head">
            <span>{hourLabel(hover)}</span>
            <span>{data.vintages.length} vintages</span>
          </div>
          {(() => {
            const selected = data.vintages.find((v) => v.publish_time_utc === data.selected_vintage_utc);
            const value = selected?.values[hover];
            const actual = data.actual_mw?.[hover] ?? null;
            const all = data.vintages
              .map((v) => v.values[hover])
              .filter((v): v is number => v !== null && v !== undefined);
            return (
              <>
                <TooltipRow
                  color="#FFB020"
                  label="At gate"
                  value={value === null || value === undefined ? "—" : `${fmtInt(value)} MW`}
                />
                {actual !== null && <TooltipRow color="#5EA8FF" label="Outturn" value={`${fmtInt(actual)} MW`} />}
                {all.length > 1 && (
                  <TooltipRow
                    label="Vintage range"
                    value={`${fmtInt(Math.min(...all))}–${fmtInt(Math.max(...all))}`}
                  />
                )}
              </>
            );
          })()}
        </ChartTooltip>
      )}
      <div className="row small muted" style={{ justifyContent: "space-between", marginTop: 6 }}>
        <span>Darker = published closer to gate closure</span>
        <span className="mono">
          {data.selected_vintage_utc
            ? `gate pick ${fmtTime(data.selected_vintage_utc)}`
            : "no vintage at gate"}
          {data.total_vintages_available > data.vintages.length
            ? ` · last ${data.vintages.length} of ${data.total_vintages_available}`
            : ""}
        </span>
      </div>
    </div>
  );
}
