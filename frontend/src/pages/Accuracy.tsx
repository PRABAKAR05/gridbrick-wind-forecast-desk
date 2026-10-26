/** Forecast Accuracy — the evidence base behind every hedge on the desk. */

import { useAccuracy, exportCsvUrl } from "@/api/queries";
import { CalibrationChart } from "@/components/charts/CalibrationChart";
import { ErrorHeatmap } from "@/components/charts/ErrorHeatmap";
import { HorizonChart } from "@/components/charts/HorizonChart";
import { ResidualHistogram } from "@/components/charts/ResidualHistogram";
import { ScatterChart } from "@/components/charts/ScatterChart";
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
  fmtDateShort,
  fmtFractionPct,
  fmtInt,
  fmtPct,
  fmtSigned,
  parseIso,
} from "@/lib/format";
import { useApp } from "@/state/app";

export function Accuracy() {
  const { cutoff, asOf } = useApp();
  const report = useAccuracy(null, null, cutoff, asOf);
  const data = report.data;

  const coverage = data?.calibration.walk_forward.table.find((row) => row.nominal === 0.8);
  const persistence = data?.benchmarks.find((row) => row.kind === "baseline" && row.name.includes("persistence"));
  const climatology = data?.benchmarks.find((row) => row.name.includes("climatology"));
  const calibrated = data?.benchmarks.find((row) => row.kind === "calibrated");

  const improvement =
    data && data.raw.mae_mw > 0 ? (1 - data.calibrated.mae_mw / data.raw.mae_mw) * 100 : null;

  return (
    <>
      <PageHead
        title="How wrong has the wind forecast been?"
        lead={
          <>
            Decision-time vintages scored against outturn, hour by hour, across the January 2026 pilot.
            The comparison is always <em>what was knowable at the gate</em> versus what actually happened.
          </>
        }
        actions={
          <>
            {data && (
              <Chip tone="muted">
                {fmtDateShort(data.window.start ?? "")} – {fmtDateShort(data.window.end ?? "")} ·{" "}
                {fmtInt(data.window.hours_evaluated)} h
              </Chip>
            )}
            <a className="btn" href={exportCsvUrl(cutoff, asOf)} download>
              Download CSV
            </a>
          </>
        }
      />

      {report.isError && <ErrorState error={report.error} onRetry={() => report.refetch()} />}

      {report.isLoading && (
        <div className="stack">
          <div className="grid grid--kpi">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} height={92} />
            ))}
          </div>
          <ChartSkeleton height={280} />
        </div>
      )}

      {data && (
        <>
          <div className="grid grid--kpi">
            <Metric
              label="Calibrated MAE"
              value={fmtInt(data.calibrated.mae_mw)}
              unit="MW"
              accent
              foot={
                <>
                  Raw {fmtInt(data.raw.mae_mw)} MW
                  {improvement !== null && <span className="t-pos">−{improvement.toFixed(0)}%</span>}
                </>
              }
            />
            <Metric
              label="RMSE"
              value={fmtInt(data.calibrated.rmse_mw)}
              unit="MW"
              foot={`R² ${data.calibrated.r2.toFixed(2)} · max ${fmtInt(data.calibrated.max_abs_error_mw)} MW`}
            />
            <Metric
              label="Bias"
              value={fmtSigned(data.calibrated.bias_mw)}
              unit="MW"
              foot={`Raw bias was ${fmtSigned(data.raw.bias_mw)} MW`}
              hint="Forecast minus outturn. Positive means the forecast ran high."
            />
            <Metric
              label="Skill vs persistence"
              value={calibrated?.skill !== null && calibrated?.skill !== undefined ? calibrated.skill.toFixed(2) : "—"}
              foot={
                persistence
                  ? `Persistence ${fmtInt(persistence.mae_mw)} MW · climatology ${fmtInt(climatology?.mae_mw)} MW`
                  : "Baseline unavailable"
              }
              hint="1 − MAE(model) / MAE(naive persistence)"
            />
            <Metric
              label="P10–P90 coverage"
              value={coverage?.observed !== null && coverage?.observed !== undefined ? fmtFractionPct(coverage.observed) : "—"}
              foot={
                coverage
                  ? `Nominal 80% · gap ${fmtFractionPct(coverage.gap, 1)} over ${fmtInt(coverage.samples)} hours`
                  : "Walk-forward not scored"
              }
              hint="Share of outturn inside the predictive band, built from earlier days only"
            />
          </div>

          <Callout tone="accent" icon="◆">
            <strong>The raw feed is biased, not just noisy.</strong> WINDFOR averaged{" "}
            {fmtSigned(data.raw.bias_mw)} MW against transmission-metered outturn, so a desk taking it at
            face value would systematically over-nominate wind. Walk-forward recalibration removes most of
            that ({fmtSigned(data.calibrated.bias_mw)} MW) and cuts MAE from {fmtInt(data.raw.mae_mw)} MW to{" "}
            {fmtInt(data.calibrated.mae_mw)} MW — out of sample, never fitted on the day being scored.
          </Callout>

          <div className="grid grid--2">
            <Panel
              title="Does an 80% band contain 80%?"
              sub="Walk-forward reliability. The diagonal is perfect calibration; dots above it are conservative."
            >
              <CalibrationChart table={data.calibration.walk_forward.table} height={258} />
            </Panel>
            <Panel
              title="Where the misses sit"
              sub="Distribution of decision-grade error (forecast − outturn)."
            >
              <ResidualHistogram scatter={data.scatter} height={258} />
            </Panel>
          </div>

          <div className="grid grid--2">
            <Panel
              title="Error by lead time"
              sub="All vintages, bucketed by hours ahead of the target hour. Skill decays slowly and honestly."
            >
              <HorizonChart rows={data.by_horizon} height={250} />
            </Panel>
            <Panel
              title="Forecast vs outturn"
              sub="Every scored hour in the pilot. The 45° line is a perfect forecast."
            >
              <ScatterChart scatter={data.scatter} height={250} />
            </Panel>
          </div>

          <Panel
            title="Error map"
            sub="Decision-grade residual by delivery day and hour of day. Red is forecast above outturn; blue is below."
            actions={<Chip tone="muted">MW</Chip>}
          >
            <ErrorHeatmap matrix={data.matrix} height={300} />
          </Panel>

          <div className="grid grid--2">
            <Panel
              title="Skill against baselines"
              sub="MAE in MW. Skill is measured against naive persistence at gate."
            >
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>MAE</th>
                      <th>Bias</th>
                      <th>Skill</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.benchmarks.map((row) => (
                      <tr key={row.name}>
                        <td className="lbl wrap">{row.name}</td>
                        <td>{fmtInt(row.mae_mw)}</td>
                        <td>{fmtSigned(row.bias_mw)}</td>
                        <td>{row.skill === null ? "—" : row.skill.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ height: 12 }} />
              <Callout icon="i">
                Persistence is deliberately hard to beat: wind is autocorrelated over a day. A model that
                cannot beat it is not earning its complexity.
              </Callout>
            </Panel>

            <Panel title="Calibration fit" sub="The affine correction currently in force, and the residual shape.">
              <KeyValue
                rows={[
                  { key: "Slope", value: data.calibration.current.slope.toFixed(3) },
                  {
                    key: "Intercept",
                    value: `${fmtSigned(data.calibration.current.intercept_mw)} MW`,
                  },
                  { key: "Fit samples", value: `${fmtInt(data.calibration.current.samples)} hours` },
                  { key: "Fit R²", value: data.calibration.current.r2.toFixed(3) },
                  {
                    key: "Band inflation",
                    value: `${data.calibration.walk_forward.inflation.toFixed(2)}×`,
                  },
                  {
                    key: "Pinball loss",
                    value: `P10 ${data.calibration.walk_forward.pinball_loss.p10?.toFixed(0) ?? "—"} · P90 ${
                      data.calibration.walk_forward.pinball_loss.p90?.toFixed(0) ?? "—"
                    }`,
                  },
                  {
                    key: "Median error",
                    value: `${fmtSigned(data.distribution.quantiles["0.5"])} MW`,
                  },
                  {
                    key: "P90 absolute error",
                    value: `${fmtInt(data.calibrated.p90_abs_error_mw)} MW`,
                  },
                  { key: "MAPE", value: fmtPct(data.calibrated.mape_pct) },
                ]}
              />
              <div style={{ height: 12 }} />
              <p className="small muted">
                Fitted on a trailing 14-day window at each gate, applied to the next day only. The
                intercept is doing the heavy lifting; the slope stays near 1 because the weather signal
                itself is sound.
              </p>
            </Panel>
          </div>

          <Panel
            title="Day by day"
            sub="The desk's daily scorecard. Calibrated error is the decision-grade number; raw is shown for comparison."
          >
            <div className="table-wrap" style={{ maxHeight: 460, overflowY: "auto" }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Delivery day</th>
                    <th>Hours</th>
                    <th>MAE</th>
                    <th>Bias</th>
                    <th>RMSE</th>
                    <th>Raw MAE</th>
                    <th>Abs energy</th>
                    <th>Bias energy</th>
                    <th>P80 cover</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_day.map((row) => (
                    <tr key={row.delivery_date}>
                      <td className="lbl">
                        {fmtDateShort(row.delivery_date)} ·{" "}
                        {new Intl.DateTimeFormat("en-GB", {
                          weekday: "short",
                          timeZone: "Europe/London",
                        }).format(parseIso(`${row.delivery_date}T12:00:00Z`))}
                      </td>
                      <td>{row.n}</td>
                      <td>{fmtInt(row.mae_mw)}</td>
                      <td>{fmtSigned(row.bias_mw)}</td>
                      <td>{fmtInt(row.rmse_mw)}</td>
                      <td className="t-dim">{fmtInt(row.raw_mae_mw)}</td>
                      <td>{fmtInt(row.abs_energy_mwh)}</td>
                      <td>{fmtSigned(row.bias_energy_mwh)}</td>
                      <td>{row.coverage_p80 === null ? "—" : fmtFractionPct(row.coverage_p80, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {data.by_day.length === 0 && (
            <EmptyState
              title="No scored days in this window"
              detail="Move the clock later, or include delivery days whose outturn has been published."
            />
          )}
        </>
      )}
    </>
  );
}
