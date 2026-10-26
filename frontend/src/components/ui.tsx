/** Presentational primitives. */

import type { CSSProperties, ReactNode } from "react";
import { fmtSigned } from "@/lib/format";

export function Panel({
  title,
  sub,
  actions,
  children,
  className,
  bodyClassName,
  style,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  style?: CSSProperties;
}) {
  return (
    <section className={`panel ${className ?? ""}`} style={style}>
      {(title || actions) && (
        <header className="panel__head">
          <div>
            {title && <h3 className="panel__title">{title}</h3>}
            {sub && <p className="panel__sub">{sub}</p>}
          </div>
          {actions && <div className="row row--tight">{actions}</div>}
        </header>
      )}
      <div className={`panel__body ${bodyClassName ?? ""}`}>{children}</div>
    </section>
  );
}

export function Metric({
  label,
  value,
  unit,
  foot,
  accent,
  hint,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  foot?: ReactNode;
  accent?: boolean;
  hint?: string;
}) {
  return (
    <div className={`metric ${accent ? "metric--accent" : ""}`} title={hint}>
      <span className="metric__label">{label}</span>
      <span className="metric__value">
        {value}
        {unit && <span className="metric__unit">{unit}</span>}
      </span>
      {foot && <span className="metric__foot">{foot}</span>}
    </div>
  );
}

export function Chip({
  children,
  tone = "neutral",
  dot,
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "live" | "pending" | "partial" | "muted" | "warn";
  dot?: boolean;
  title?: string;
}) {
  const className =
    tone === "live"
      ? "chip chip--live"
      : tone === "pending"
        ? "chip chip--pending"
        : tone === "partial"
          ? "chip chip--partial"
          : tone === "muted"
            ? "chip chip--muted"
            : tone === "warn"
              ? "chip chip--warn"
              : "chip";
  return (
    <span className={className} title={title}>
      {dot && <span className={`dot ${tone === "live" ? "dot--pulse" : ""}`} />}
      {children}
    </span>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: T; label: string; title?: string }[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="segmented__btn"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          title={option.title}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Legend({
  items,
}: {
  items: { label: string; color: string; kind?: "line" | "area" | "dash"; off?: boolean; onClick?: () => void }[];
}) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span
          key={item.label}
          className="legend__item"
          data-off={item.off ? "true" : "false"}
          onClick={item.onClick}
          role={item.onClick ? "button" : undefined}
          tabIndex={item.onClick ? 0 : undefined}
          onKeyDown={(event) => {
            if (item.onClick && (event.key === "Enter" || event.key === " ")) {
              event.preventDefault();
              item.onClick();
            }
          }}
        >
          <span
            className={`legend__swatch ${item.kind === "area" ? "legend__swatch--area" : ""} ${
              item.kind === "dash" ? "legend__swatch--dash" : ""
            }`}
            style={
              item.kind === "area"
                ? { background: item.color }
                : item.kind === "dash"
                  ? { color: item.color }
                  : { background: item.color }
            }
          />
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function Delta({
  value,
  digits = 0,
  invert = false,
  suffix,
}: {
  value: number | null | undefined;
  digits?: number;
  invert?: boolean;
  suffix?: string;
}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="muted">—</span>;
  }
  const good = invert ? value < 0 : value > 0;
  const bad = invert ? value > 0 : value < 0;
  const className = good ? "t-pos" : bad ? "t-neg" : "t-dim";
  return (
    <span className={`mono ${className}`}>
      {fmtSigned(value, digits)}
      {suffix}
    </span>
  );
}

export function Skeleton({ height = 16, width = "100%" }: { height?: number | string; width?: string }) {
  return <div className="skeleton" style={{ height, width }} />;
}

export function ChartSkeleton({ height = 240 }: { height?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading chart">
      <Skeleton height={height} />
      <Skeleton height={12} width="40%" />
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="error-box" role="alert">
      <strong>Couldn’t load this view</strong>
      <code>{message}</code>
      {onRetry && (
        <div>
          <button type="button" className="btn" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: ReactNode }) {
  return (
    <div className="empty">
      <strong style={{ color: "var(--text-2)", fontWeight: 500 }}>{title}</strong>
      {detail && <span style={{ maxWidth: "52ch" }}>{detail}</span>}
    </div>
  );
}

export function Callout({
  children,
  tone = "neutral",
  icon = "◆",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "warn";
  icon?: ReactNode;
}) {
  const className =
    tone === "accent" ? "callout callout--accent" : tone === "warn" ? "callout callout--warn" : "callout";
  return (
    <div className={className}>
      <span className="callout__icon" aria-hidden="true">
        {icon}
      </span>
      <div>{children}</div>
    </div>
  );
}

export function KeyValue({ rows }: { rows: { key: ReactNode; value: ReactNode }[] }) {
  return (
    <div className="kv">
      {rows.map((row, index) => (
        <div className="kv__row" key={index}>
          <span className="kv__key">{row.key}</span>
          <span className="kv__val">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

export function PageHead({
  title,
  lead,
  actions,
}: {
  title: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="page-head__copy">
        <h1 className="page-head__title">{title}</h1>
        {lead && <p className="page-head__lead">{lead}</p>}
      </div>
      {actions && <div className="row row--tight">{actions}</div>}
    </header>
  );
}
