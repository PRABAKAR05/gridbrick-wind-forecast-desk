/** Shared chart scaffolding: responsive sizing, axes, grid, hover tooltip. */

import { useEffect, useRef, useState, type ReactNode } from "react";

export function useChartSize(fallback = 720) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    setWidth(element.clientWidth || fallback);
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width;
      if (next && next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [fallback]);

  return { ref, width };
}

export interface Margin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export const DEFAULT_MARGIN: Margin = { top: 14, right: 14, bottom: 24, left: 46 };

export function Axes({
  x,
  y,
  xTicks,
  yTicks,
  inner,
  xFormat,
  yFormat,
  showXGrid = false,
  showYGrid = true,
  yLabel,
}: {
  x: (value: number) => number;
  y: (value: number) => number;
  xTicks: number[];
  yTicks: number[];
  inner: { left: number; top: number; width: number; height: number };
  xFormat?: (value: number) => string;
  yFormat?: (value: number) => string;
  showXGrid?: boolean;
  showYGrid?: boolean;
  yLabel?: string;
}) {
  return (
    <g className="chart__axis">
      {showYGrid &&
        yTicks.map((tick) => (
          <line
            key={`gy-${tick}`}
            className="chart__grid"
            x1={inner.left}
            x2={inner.left + inner.width}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--line)"
            strokeWidth={1}
          />
        ))}
      {showXGrid &&
        xTicks.map((tick) => (
          <line
            key={`gx-${tick}`}
            x1={x(tick)}
            x2={x(tick)}
            y1={inner.top}
            y2={inner.top + inner.height}
            stroke="var(--line)"
            strokeWidth={1}
          />
        ))}
      {yTicks.map((tick) => (
        <text
          key={`ty-${tick}`}
          x={inner.left - 8}
          y={y(tick)}
          textAnchor="end"
          dominantBaseline="middle"
        >
          {yFormat ? yFormat(tick) : tick}
        </text>
      ))}
      {xTicks.map((tick) => (
        <text
          key={`tx-${tick}`}
          x={x(tick)}
          y={inner.top + inner.height + 15}
          textAnchor="middle"
        >
          {xFormat ? xFormat(tick) : tick}
        </text>
      ))}
      {yLabel && (
        <text className="chart__label" x={inner.left - 34} y={inner.top - 4}>
          {yLabel}
        </text>
      )}
      <line
        x1={inner.left}
        x2={inner.left}
        y1={inner.top}
        y2={inner.top + inner.height}
        stroke="var(--line-2)"
      />
      <line
        x1={inner.left}
        x2={inner.left + inner.width}
        y1={inner.top + inner.height}
        y2={inner.top + inner.height}
        stroke="var(--line-2)"
      />
    </g>
  );
}

export function ChartTooltip({
  left,
  top,
  width,
  children,
}: {
  left: number;
  top: number;
  width: number;
  children: ReactNode;
}) {
  const flip = left > width - 190;
  return (
    <div
      className="tooltip"
      style={{
        left: flip ? undefined : left + 14,
        right: flip ? Math.max(8, width - left + 14) : undefined,
        top: Math.max(4, top - 8),
      }}
      role="status"
    >
      {children}
    </div>
  );
}

export function TooltipRow({
  color,
  label,
  value,
}: {
  color?: string;
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="tooltip__row">
      <span className="tooltip__key">
        {color && (
          <span
            style={{
              width: 8,
              height: 2,
              borderRadius: 1,
              background: color,
              display: "inline-block",
            }}
          />
        )}
        {label}
      </span>
      <span className="tooltip__val">{value}</span>
    </div>
  );
}
