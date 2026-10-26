/** Day x hour error heatmap: where in the month did the forecast hurt? */

import { useMemo, useState } from "react";
import type { AccuracyReport } from "@/api/types";
import { diverging } from "@/lib/chart";
import { fmtSigned, hourLabel } from "@/lib/format";
import { ChartTooltip, TooltipRow, useChartSize } from "./Shell";

const MARGIN = { top: 6, right: 8, bottom: 20, left: 40 };

export function ErrorHeatmap({
  matrix,
  height = 300,
}: {
  matrix: AccuracyReport["matrix"];
  height?: number;
}) {
  const { ref, width } = useChartSize();
  const [hover, setHover] = useState<{ row: number; col: number } | null>(null);

  const inner = {
    left: MARGIN.left,
    top: MARGIN.top,
    width: Math.max(10, width - MARGIN.left - MARGIN.right),
    height: Math.max(10, height - MARGIN.top - MARGIN.bottom),
  };

  const scale = useMemo(() => {
    const values = matrix.flatMap((row) => row.residuals).filter((v): v is number => v !== null);
    if (!values.length) return 1000;
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length * 0.9)] ?? 1000;
  }, [matrix]);

  const colWidth = inner.width / 24;
  const rowHeight = inner.height / Math.max(1, matrix.length);
  const cell = hover ? matrix[hover.row]?.residuals[hover.col] ?? null : null;

  return (
    <div className="chart" ref={ref}>
      <svg width="100%" height={height} role="img" aria-label="Residual heatmap by day and hour">
        {matrix.map((row, rowIndex) => {
          const showLabel = rowIndex % Math.max(1, Math.ceil(matrix.length / 8)) === 0;
          return (
            <g key={row.delivery_date}>
              {showLabel && (
                <text
                  x={inner.left - 8}
                  y={inner.top + rowIndex * rowHeight + rowHeight / 2}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fill="var(--text-3)"
                  fontSize={9}
                  className="mono"
                >
                  {row.delivery_date.slice(8)}/{row.delivery_date.slice(5, 7)}
                </text>
              )}
              {row.residuals.map((value, colIndex) => (
                <rect
                  key={colIndex}
                  x={inner.left + colIndex * colWidth}
                  y={inner.top + rowIndex * rowHeight}
                  width={Math.max(1, colWidth - 1)}
                  height={Math.max(1, rowHeight - 1)}
                  rx={1}
                  fill={value === null ? "transparent" : diverging(value, scale)}
                  stroke={
                    hover?.row === rowIndex && hover?.col === colIndex ? "var(--text)" : "transparent"
                  }
                  strokeWidth={1}
                  onMouseEnter={() => setHover({ row: rowIndex, col: colIndex })}
                />
              ))}
            </g>
          );
        })}

        {[0, 6, 12, 18, 23].map((hour) => (
          <text
            key={hour}
            x={inner.left + (hour + 0.5) * colWidth}
            y={inner.top + inner.height + 14}
            textAnchor="middle"
            fill="var(--text-3)"
            fontSize={9}
            className="mono"
          >
            {hourLabel(hour).slice(0, 2)}
          </text>
        ))}
      </svg>

      <div className="row small muted" style={{ justifyContent: "space-between", marginTop: 4 }}>
        <span className="row row--tight">
          <span>Under-forecast</span>
          <span
            style={{
              width: 92,
              height: 7,
              borderRadius: 2,
              background: "linear-gradient(90deg, rgba(94,168,255,0.8), rgba(94,168,255,0.08), rgba(255,107,107,0.08), rgba(255,107,107,0.8))",
              display: "inline-block",
            }}
          />
          <span>Over-forecast</span>
        </span>
        <span className="mono">±{Math.round(scale)} MW scale</span>
      </div>

      {hover && (
        <ChartTooltip
          left={inner.left + (hover.col + 0.5) * colWidth}
          top={inner.top + hover.row * rowHeight}
          width={width}
        >
          <div className="tooltip__head">
            <span>{matrix[hover.row]?.delivery_date}</span>
            <span>{hourLabel(hover.col)}</span>
          </div>
          <TooltipRow
            label="Error"
            value={
              cell === null ? (
                "—"
              ) : (
                <span className={cell > 0 ? "t-neg" : "t-pos"}>{fmtSigned(cell)} MW</span>
              )
            }
          />
        </ChartTooltip>
      )}
    </div>
  );
}
