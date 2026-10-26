/** Application chrome: navigation, the delivery-day clock, and the status line.
 *
 *  The top bar is deliberately the only place that mutates the clock. Every
 *  page below it is a pure function of the URL state, so two people can look at
 *  the same URL and see the same numbers.
 */

import { useEffect, useState, type ReactNode } from "react";
import { useDeliveryDays } from "@/api/queries";
import { Chip } from "@/components/ui";
import {
  addDays,
  fmtDateLong,
  fmtDateShort,
  fmtDateTime,
  fmtWeekday,
  isoToLocalInput,
  londonWallTimeIso,
} from "@/lib/format";
import { useApp, type RouteName } from "@/state/app";

const ROUTES: { id: RouteName; label: string; blurb: string }[] = [
  { id: "desk", label: "Decision Desk", blurb: "What the market knew at gate closure" },
  { id: "accuracy", label: "Forecast Accuracy", blurb: "How wrong the forecast has been" },
  { id: "procurement", label: "Procurement", blurb: "Turning error into a hedging decision" },
  { id: "method", label: "Method & Limits", blurb: "Data, calibration and honest caveats" },
];

const SHORT_LABELS: Record<RouteName, string> = {
  desk: "Desk",
  accuracy: "Accuracy",
  procurement: "Hedge",
  method: "Method",
};

const STATUS: Record<string, { tone: "live" | "pending" | "partial" | "muted"; label: string }> = {
  realised: { tone: "live", label: "Outturn complete" },
  partial: { tone: "partial", label: "Partial outturn" },
  awaiting_outturn: { tone: "pending", label: "Awaiting outturn" },
  pending_gate: { tone: "muted", label: "Pre-gate" },
};

function NavIcon({ route }: { route: RouteName }) {
  if (route === "accuracy") {
    return (
      <svg className="nav__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="8" cy="8" r="1.6" fill="currentColor" />
        <path d="M8 1v2.2M8 12.8V15M1 8h2.2M12.8 8H15" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    );
  }
  if (route === "procurement") {
    return (
      <svg className="nav__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M2 14V9h3v5M6.5 14V4h3v10M11 14V6.5h3V14" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    );
  }
  if (route === "method") {
    return (
      <svg className="nav__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M2.5 2.5h6a2 2 0 012 2v9h-6a2 2 0 00-2 2v-13Z" stroke="currentColor" strokeWidth="1.2" />
        <path d="M13.5 2.5h-3v11.5h1a2 2 0 002-2V2.5Z" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    );
  }
  return (
    <svg className="nav__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
      <rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" opacity=".45" />
      <rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" opacity=".45" />
      <rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function BrandMark() {
  return (
    <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#0f1319" stroke="#262f3a" />
      <g fill="var(--accent)">
        <rect x="7" y="7" width="7" height="7" rx="1.5" />
        <rect x="18" y="7" width="7" height="7" rx="1.5" opacity=".35" />
        <rect x="7" y="18" width="7" height="7" rx="1.5" opacity=".35" />
        <rect x="18" y="18" width="7" height="7" rx="1.5" />
      </g>
    </svg>
  );
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function Layout({ children }: { children: ReactNode }) {
  const {
    route,
    navigate,
    meta,
    deliveryDate,
    setDeliveryDate,
    cutoff,
    setCutoff,
    asOf,
    setAsOf,
    pilotDays,
  } = useApp();

  const daysQuery = useDeliveryDays(asOf, cutoff);
  const day = daysQuery.data?.days.find((row) => row.delivery_date === deliveryDate);
  const status = day ? STATUS[day.status] : undefined;

  const gateIso = londonWallTimeIso(addDays(deliveryDate, -1), cutoff.hour, cutoff.minute);
  const outturnIso = londonWallTimeIso(addDays(deliveryDate, 1), 12, 0);

  const [custom, setCustom] = useState(asOf ? isoToLocalInput(asOf) : "");
  useEffect(() => {
    setCustom(asOf ? isoToLocalInput(asOf) : "");
  }, [asOf]);

  const active = asOf === null ? "live" : asOf === gateIso ? "gate" : asOf === outturnIso ? "outturn" : "custom";
  const activeRoute = ROUTES.find((item) => item.id === route) ?? ROUTES[0]!;

  const setPreset = (preset: "live" | "gate" | "outturn" | "custom") => {
    if (preset === "live") setAsOf(null);
    else if (preset === "gate") setAsOf(gateIso);
    else if (preset === "outturn") setAsOf(outturnIso);
    else setAsOf(new Date(Date.parse(gateIso) + 12 * 3_600_000).toISOString());
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <BrandMark />
          <div>
            <div className="brand__name">GridBrick</div>
            <div className="brand__sub">Forecast Desk</div>
          </div>
        </div>

        <nav className="nav" aria-label="Primary">
          <div className="nav__label">Workspace</div>
          {ROUTES.map((item) => (
            <a
              key={item.id}
              className={`nav__item ${route === item.id ? "nav__item--active" : ""}`}
              href={`#/${item.id}`}
              aria-label={item.label}
              aria-current={route === item.id ? "page" : undefined}
              onClick={(event) => {
                event.preventDefault();
                navigate(item.id);
              }}
            >
              <NavIcon route={item.id} />
              <span className="nav__full">{item.label}</span>
              <span className="nav__short" aria-hidden="true">
                {SHORT_LABELS[item.id]}
              </span>
            </a>
          ))}
        </nav>

        <div className="sidebar__foot">
          <div className="spread">
            <span>Data</span>
            <strong>Elexon BMRS</strong>
          </div>
          <div className="spread">
            <span>Vintages</span>
            <strong className="mono">{meta.data.vintages}</strong>
          </div>
          <div className="spread">
            <span>Latest obs.</span>
            <strong className="mono">
              {meta.data.latest_observable_utc ? fmtDateTime(meta.data.latest_observable_utc) : "—"}
            </strong>
          </div>
          <div className="spread">
            <span>Version</span>
            <strong className="mono">v{meta.version}</strong>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar__title">
            <span className="topbar__eyebrow">{activeRoute.blurb}</span>
            <span className="topbar__h">{activeRoute.label}</span>
          </div>

          <div className="topbar__spacer" />

          <label className="field">
            <span className="field__label">Delivery day</span>
            <select
              className="select"
              value={deliveryDate}
              onChange={(event) => setDeliveryDate(event.target.value)}
              title={fmtDateLong(deliveryDate)}
            >
              {pilotDays.map((iso) => (
                <option key={iso} value={iso}>
                  {fmtWeekday(iso)} {fmtDateShort(iso)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field__label">Gate</span>
            <input
              className="select"
              type="time"
              value={`${pad(cutoff.hour)}:${pad(cutoff.minute)}`}
              onChange={(event) => {
                const [hour, minute] = event.target.value.split(":").map(Number);
                if (Number.isFinite(hour) && Number.isFinite(minute)) setCutoff(hour!, minute!);
              }}
              title="Local (Europe/London) day-ahead gate closure on D-1"
            />
          </label>

          <div className="field">
            <span className="field__label">Clock</span>
            <div className="segmented" role="group" aria-label="Point-in-time clock">
              {(
                [
                  { id: "live", label: "Live" },
                  { id: "gate", label: "At gate" },
                  { id: "outturn", label: "D+1" },
                  { id: "custom", label: "Custom" },
                ] as const
              ).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="segmented__btn"
                  aria-pressed={active === item.id}
                  onClick={() => setPreset(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {active === "custom" && (
              <input
                className="select select--clock"
                type="datetime-local"
                value={custom}
                onChange={(event) => {
                  setCustom(event.target.value);
                  if (event.target.value) {
                    const parsed = new Date(event.target.value);
                    if (!Number.isNaN(parsed.getTime())) setAsOf(parsed.toISOString());
                  }
                }}
                aria-label="Custom as-of instant"
                title="Custom point-in-time clock (browser local time)"
              />
            )}
          </div>

          {status ? (
            <Chip tone={status.tone} dot title={`Status at ${daysQuery.data?.as_of_utc ?? ""}`}>
              {status.label}
            </Chip>
          ) : (
            <Chip tone="muted">Loading clock</Chip>
          )}
        </header>

        <div className="content">{children}</div>
      </main>
    </div>
  );
}
