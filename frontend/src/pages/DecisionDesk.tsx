/** Decision Desk — the point-in-time view a trader sees at gate closure. */

import { useVintages, useDecision } from "@/api/queries";
import type { DecisionHour } from "@/api/types";
import { ForecastBandChart } from "@/components/charts/ForecastBandChart";
import { VintageEvolutionChart } from "@/components/charts/VintageEvolutionChart";
import {
  Callout,
  ChartSkeleton,
  Chip,
  EmptyState,
  ErrorState,
  KeyValue,
  Metric,
  PageHead,
  Panel,
  Skeleton,
} from "@/components/ui";
import {
  fmtDateLong,
  fmtDateTime,
  fmtFractionPct,
  fmtGwh,
  fmtInt,
  fmtSigned,
  fmtTime,
  hourLabel,
  parseIso,
} from "@/lib/format";
import { useApp } from "@/state/app";

function HourTable({ hours }: { hours: DecisionHour[] }) {
  return (
    <div className="table-wrap" style={{ maxHeight: 430, overflowY: "auto" }}>
      <table className="data">
        <thead>
          <tr>
            <th>Hour</th>
            <th>Lead</th>
            <th>Raw WINDFOR</th>
            <th>Decision-grade</th>
            <th>P10</th>
            <th>P90</th>
            <th>Outturn</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {hours.map((row) => (
            <tr key={row.hour}>
              <td>{hourLabel(row.hour)}</td>
              <td className="muted">{row.lead_hours !== null ? `${row.lead_hours.toFixed(1)}h` : "—"}</td>
              <td className="t-dim">{fmtInt(row.forecast_mw)}</td>
              <td className="t-accent">{fmtInt(row.calibrated_mw)}</td>
              <td className="t-dim">{fmtInt(row.band?.p10)}</td>
              <td className="t-dim">{fmtInt(row.band?.p90)}</td>
              <td>{fmtInt(row.actual_mw)}</td>
              <td className={row.residual_mw === null ? "muted" : "t-dim"}>
                {fmtSigned(row.residual_mw)} {row.residual_mw === null ? "" : "MW"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DecisionDesk() {
  const { deliveryDate, cutoff, asOf } = useApp();
  const decision = useDecision(deliveryDate, cutoff, asOf);
  const vintages = useVintages(deliveryDate, cutoff, asOf);

  const data = decision.data;
  const summary = data?.summary;
  const preGate = data ? parseIso(data.as_of_utc) < parseIso(data.cutoff_utc) : false;
  const bandWidth =
    summary?.wind_p90_mwh !== null && summary?.wind_p90_mwh !== undefined && summary.wind_p10_mwh !== null
      ? (summary.wind_p90_mwh - summary.wind_p10_mwh) / 1000
      : null;

  return (
    <>
      <PageHead
        title={`Wind, as it stood at ${String(cutoff.hour).padStart(2, "0")}:${String(cutoff.minute).padStart(2, "0")}`}
        lead={
          <>
            Latest Elexon WINDFOR vintage published <em>before</em> the day-ahead gate, recalibrated against
            transmission-metered outturn. Every number on this page is filtered by the clock in the top bar.
          </>
        }
        actions={
          <>
            <Chip tone={asOf ? "partial" : "live"} dot>
              {asOf ? "Historical clock" : "Live clock"}
            </Chip>
            <a className="btn" href="#/accuracy">
              See the error record
            </a>
          </>
        }
      />

      {decision.isError && <ErrorState error={decision.error} onRetry={() => decision.refetch()} />}

      {decision.isLoading && (
        <div className="stack">
          <div className="grid grid--kpi">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} height={92} />
            ))}
          </div>
          <ChartSkeleton height={320} />
        </div>
      )}

      {data && summary && (
        <>
          {preGate && (
            <Callout tone="accent" icon="!">
              <strong>This clock is before gate closure.</strong> The desk has not yet reached the decision
              point for {fmtDateLong(deliveryDate)}. Move the clock to <em>At gate</em> to see the vintage
              that would actually have been used.
            </Callout>
          )}

          {!data.vintage.available && (
            <Callout tone="warn" icon="!">
              <strong>No usable vintage.</strong> {data.vintage.note} Try a later clock or a different
              delivery day.
            </Callout>
          )}

          <div className="grid grid--kpi">
            <Metric
              label="Decision-grade wind"
              value={fmtGwh(summary.wind_calibrated_mwh)}
              unit="GWh"
              accent
              foot={
                <>
                  Raw feed {fmtGwh(summary.wind_forecast_mwh)} GWh
                  {summary.wind_forecast_mwh !== null && summary.wind_calibrated_mwh !== null && (
                    <span className="mono">
                      ({fmtSigned(summary.wind_calibrated_mwh - summary.wind_forecast_mwh)} MWh)
                    </span>
                  )}
                </>
              }
              hint="Walk-forward affine recalibration applied out-of-sample"
            />
            <Metric
              label="P10 – P90 range"
              value={bandWidth === null ? "—" : bandWidth.toFixed(1)}
              unit="GWh"
              foot={
                summary.band.available
                  ? `${summary.band.usable_days} days · ${fmtInt(summary.band.samples)} residuals`
                  : (summary.band.reason ?? "Band unavailable")
              }
              hint="Empirical residual quantiles, inflated for conformal coverage"
            />
            <Metric
              label="Nominated wind"
              value={fmtGwh(summary.wind_nominated_mwh)}
              unit="GWh"
              foot={
                summary.nomination_uplift_mwh === null
                  ? "Risk calc unavailable"
                  : `${fmtSigned(summary.nomination_uplift_mwh)} MWh vs point forecast`
              }
              hint="Decision-grade wind plus a procurement hedge offset"
            />
            <Metric
              label="Expected shortfall"
              value={fmtGwh(summary.expected_shortfall_mwh)}
              unit="GWh"
              foot={
                summary.prob_short === null
                  ? "No band"
                  : `${fmtFractionPct(summary.prob_short)} of hours short · ${fmtGwh(
                      summary.expected_surplus_mwh,
                    )} GWh long`
              }
            />
            <Metric
              label="Realised error"
              value={summary.realised ? fmtInt(summary.mae_mw) : "—"}
              unit={summary.realised ? "MW MAE" : undefined}
              foot={
                summary.realised ? (
                  <>
                    Bias {fmtSigned(summary.bias_mw)} MW · raw {fmtInt(summary.raw_mae_mw)} MW
                  </>
                ) : (
                  "Outturn not yet complete"
                )
              }
            />
          </div>

          <div className="grid grid--main">
            <Panel
              title="Forecast at gate closure"
              sub={
                data.vintage.publish_time_utc
                  ? `Vintage published ${fmtDateTime(data.vintage.publish_time_utc)} · ${data.vintage.age_hours?.toFixed(
                      1,
                    )} h stale at gate · ${data.vintage.horizon_hours ?? "—"} h ahead`
                  : data.vintage.note
              }
            >
              {data.hours.length ? (
                <ForecastBandChart hours={data.hours} realised={summary.realised} height={312} />
              ) : (
                <EmptyState title="No hours available" detail={data.vintage.note} />
              )}
            </Panel>

            <Panel title="Read this before you trade" sub="Provenance and assumptions behind the chart.">
              <KeyValue
                rows={[
                  { key: "Delivery day", value: fmtDateLong(deliveryDate) },
                  { key: "Gate closure", value: fmtDateTime(data.cutoff_utc) },
                  {
                    key: "Vintage used",
                    value: data.vintage.publish_time_utc
                      ? `${fmtTime(data.vintage.publish_time_utc)} · ${fmtDateLong(data.vintage.publish_time_utc)}`
                      : "None",
                  },
                  {
                    key: "Vintage age",
                    value: data.vintage.age_hours !== null ? `${data.vintage.age_hours.toFixed(1)} h` : "—",
                  },
                  {
                    key: "Calibration",
                    value: `${summary.calibration.slope.toFixed(3)} × forecast ${
                      summary.calibration.intercept_mw >= 0 ? "+" : "−"
                    } ${fmtInt(Math.abs(summary.calibration.intercept_mw))} MW`,
                  },
                  {
                    key: "Fit sample",
                    value: `${fmtInt(summary.calibration.samples)} hours · R² ${summary.calibration.r2.toFixed(2)}`,
                  },
                  {
                    key: "Band sample",
                    value: summary.band.available
                      ? `${summary.band.usable_days} days · ${fmtInt(summary.band.samples)} residuals`
                      : (summary.band.reason ?? "Unavailable"),
                  },
                  {
                    key: "Cost policy",
                    value: `α = ${fmtFractionPct(summary.policy.critical_fractile)} (short ${summary.policy.c_short} / long ${summary.policy.c_long})`,
                  },
                ]}
              />
              <div style={{ height: 12 }} />
              <Callout icon="i">
                The raw WINDFOR feed carries a structural level bias against transmission-metered
                outturn. The calibrated line is what this desk would actually trade; the raw feed is
                shown so the correction is auditable rather than hidden.
              </Callout>
              <div style={{ height: 12 }} />
              <a className="btn btn--accent" href="#/procurement">
                Size the thermal hedge →
              </a>
            </Panel>
          </div>

          <Panel
            title="How the forecast moved before gate"
            sub="Each line is one published WINDFOR vintage for this delivery day. The highlighted line is the last one visible at the gate."
            actions={
              <Chip tone="muted">
                {vintages.data?.total_vintages_available ?? 0} vintages on record
              </Chip>
            }
          >
            {vintages.isLoading && <ChartSkeleton height={210} />}
            {vintages.isError && <ErrorState error={vintages.error} onRetry={() => vintages.refetch()} />}
            {vintages.data && vintages.data.vintages.length > 0 && (
              <VintageEvolutionChart data={vintages.data} height={220} />
            )}
            {vintages.data && vintages.data.vintages.length === 0 && (
              <EmptyState
                title="No vintages before this clock"
                detail="Move the clock forward, or pick a delivery day with published forecasts."
              />
            )}
          </Panel>

          <Panel
            title="Hourly detail"
            sub="Hourly MW. Positive error means the decision-grade forecast was above outturn (the desk would have been nominally long)."
            actions={
              <Chip tone={summary.realised ? "live" : "pending"}>
                {summary.hours_with_actual}/24 hours realised
              </Chip>
            }
          >
            <HourTable hours={data.hours} />
          </Panel>
        </>
      )}
    </>
  );
}
