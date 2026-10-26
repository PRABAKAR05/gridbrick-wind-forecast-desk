/** Procurement — where quantified forecast error becomes a quantity to buy. */

import { useMemo, useState } from "react";
import { usePlan, type PlanRequest } from "@/api/queries";
import { ThermalChart } from "@/components/charts/ThermalChart";
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
  Segmented,
  Skeleton,
} from "@/components/ui";
import {
  fmtDateLong,
  fmtDateTime,
  fmtFractionPct,
  fmtGwh,
  fmtInt,
  fmtPct,
  fmtSigned,
  hourLabel,
} from "@/lib/format";
import { useApp } from "@/state/app";

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 500,
  unit,
  hint,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  unit: string;
  hint?: string;
}) {
  return (
    <label className="control">
      <span className="control__label">
        {label}
        <span className="control__unit">{unit}</span>
      </span>
      <input
        className="control__range"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <input
        className="select control__num"
        type="number"
        min={min}
        step={step}
        value={value}
        aria-label={`${label} exact value`}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) onChange(next);
        }}
      />
      {hint && <span className="control__hint">{hint}</span>}
    </label>
  );
}

export function Procurement() {
  const { meta, deliveryDate, cutoff, asOf } = useApp();
  const [profile, setProfile] = useState<"synthetic_gb_winter" | "flat">("synthetic_gb_winter");
  const [peak, setPeak] = useState(46_000);
  const [trough, setTrough] = useState(30_000);
  const [flat, setFlat] = useState(38_000);
  const [cShort, setCShort] = useState(meta.defaults.c_short);
  const [cLong, setCLong] = useState(meta.defaults.c_long);

  const body: PlanRequest = useMemo(
    () => ({
      delivery_date: deliveryDate,
      as_of: asOf,
      cutoff_hour: cutoff.hour,
      cutoff_minute: cutoff.minute,
      demand_profile: profile,
      peak_mw: peak,
      trough_mw: Math.min(trough, peak - 1_000),
      flat_mw: flat,
      c_short: cShort,
      c_long: cLong,
    }),
    [deliveryDate, asOf, cutoff.hour, cutoff.minute, profile, peak, trough, flat, cShort, cLong],
  );

  const plan = usePlan(body);
  const data = plan.data;
  const alpha = cLong / (cShort + cLong);

  const avgOffset = useMemo(() => {
    const values = (data?.hours ?? [])
      .map((row) => row.exposure?.offset_mw)
      .filter((value): value is number => value !== null && value !== undefined);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }, [data]);

  const upliftPct =
    data?.totals.thermal_baseline_mwh && data.totals.risk_uplift_mwh !== null
      ? (data.totals.risk_uplift_mwh / data.totals.thermal_baseline_mwh) * 100
      : null;

  const reset = () => {
    setProfile("synthetic_gb_winter");
    setPeak(46_000);
    setTrough(30_000);
    setFlat(38_000);
    setCShort(meta.defaults.c_short);
    setCLong(meta.defaults.c_long);
  };

  return (
    <>
      <PageHead
        title="How much thermal should the desk buy?"
        lead={
          <>
            A newsvendor calculation, not a forecast. Wind is nominated at a quantile of its predictive
            distribution; the gap to demand is procured as thermal. Move the cost ratio and watch the hedge
            move.
          </>
        }
        actions={
          <>
            <Chip tone="muted">Demand is an illustrative input</Chip>
            <button type="button" className="btn" onClick={reset}>
              Reset policy
            </button>
          </>
        }
      />

      <Panel
        title="Policy and demand inputs"
        sub={meta.demand_profiles.find((item) => item.id === profile)?.description}
        actions={<Chip tone={profile === "flat" ? "muted" : "partial"}>{profile === "flat" ? "Flat block" : "Synthetic shape"}</Chip>}
      >
        <div className="control-grid">
          <div className="control">
            <span className="control__label">Demand profile</span>
            <Segmented
              ariaLabel="Demand profile"
              value={profile}
              onChange={(value) => setProfile(value)}
              options={meta.demand_profiles.map((item) => ({ value: item.id as typeof profile, label: item.label }))}
            />
            <span className="control__hint">
              Replace with the desk's own demand signal in production. Not modelled here.
            </span>
          </div>

          {profile === "synthetic_gb_winter" ? (
            <>
              <NumberField
                label="Peak demand"
                value={peak}
                onChange={setPeak}
                min={36_000}
                max={56_000}
                unit="MW"
                hint="Evening peak of the winter shape"
              />
              <NumberField
                label="Trough demand"
                value={trough}
                onChange={setTrough}
                min={20_000}
                max={40_000}
                unit="MW"
                hint="Overnight trough"
              />
            </>
          ) : (
            <NumberField
              label="Flat demand"
              value={flat}
              onChange={setFlat}
              min={20_000}
              max={56_000}
              unit="MW"
              hint="Constant across all 24 hours"
            />
          )}

          <NumberField
            label="Cost of being short"
            value={cShort}
            onChange={setCShort}
            min={0.5}
            max={5}
            step={0.1}
            unit="×"
            hint={`c_short = ${cShort.toFixed(1)} per MWh`}
          />
          <NumberField
            label="Cost of being long"
            value={cLong}
            onChange={setCLong}
            min={0.5}
            max={3}
            step={0.1}
            unit="×"
            hint={`c_long = ${cLong.toFixed(1)} per MWh`}
          />

          <div className="control control--readout">
            <span className="control__label">Critical fractile</span>
            <span className="control__big mono">{fmtFractionPct(alpha)}</span>
            <span className="control__hint">
              α = c_long / (c_short + c_long). Nominate wind at the α-quantile; the remaining 1 − α is the
              shortfall you are deliberately hedging.
            </span>
          </div>
        </div>
      </Panel>

      {plan.isError && <ErrorState error={plan.error} onRetry={() => plan.refetch()} />}

      {plan.isLoading && (
        <div className="stack">
          <div className="grid grid--kpi">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} height={92} />
            ))}
          </div>
          <ChartSkeleton height={300} />
        </div>
      )}

      {data && (
        <>
          <div className="grid grid--kpi">
            <Metric
              label="Demand input"
              value={fmtGwh(data.totals.demand_mwh)}
              unit="GWh"
              foot={fmtDateLong(data.delivery_date)}
            />
            <Metric
              label="Wind nominated"
              value={fmtGwh(data.totals.wind_nominated_mwh)}
              unit="GWh"
              foot={
                <>
                  Decision-grade {fmtGwh(data.forecast.summary.wind_calibrated_mwh)} GWh
                  {avgOffset !== null && <span className="mono"> · offset {fmtSigned(avgOffset)} MW</span>}
                </>
              }
              hint="Calibrated point forecast plus the newsvendor hedge offset"
            />
            <Metric
              label="Thermal procured"
              value={fmtGwh(data.totals.thermal_procured_mwh)}
              unit="GWh"
              accent
              foot={`Nominal ${fmtGwh(data.totals.thermal_baseline_mwh)} GWh`}
            />
            <Metric
              label="Risk uplift"
              value={fmtGwh(data.totals.risk_uplift_mwh)}
              unit="GWh"
              foot={upliftPct === null ? "—" : `${fmtPct(upliftPct, 1)} more thermal than nominal`}
              hint="The cost of buying insurance against wind undershoot"
            />
            <Metric
              label="Expected shortfall"
              value={fmtGwh(data.totals.expected_shortfall_mwh)}
              unit="GWh"
              foot={`${data.totals.hours_covered} hours priced · ${fmtFractionPct(
                data.forecast.summary.prob_short,
              )} short probability`}
            />
          </div>

          <div className="grid grid--main">
            <Panel
              title="Thermal cover through the day"
              sub="The amber line is what the desk buys; the dashed line is what it would buy if it trusted the point forecast. The wedge is the risk premium."
              actions={
                <Chip tone="muted">
                  α = {fmtFractionPct(data.policy.critical_fractile)}
                </Chip>
              }
            >
              {data.hours.length ? (
                <ThermalChart hours={data.hours} height={300} />
              ) : (
                <EmptyState title="No plan for this clock" detail="No usable vintage or demand input." />
              )}
            </Panel>

            <Panel title="Why this quantity" sub="The decision rule, the inputs, and what it costs.">
              <KeyValue
                rows={[
                  { key: "Delivery day", value: fmtDateLong(data.delivery_date) },
                  { key: "Gate closure", value: fmtDateTime(data.cutoff_utc) },
                  {
                    key: "Vintage",
                    value: data.forecast.vintage.publish_time_utc
                      ? fmtDateTime(data.forecast.vintage.publish_time_utc)
                      : "None",
                  },
                  { key: "Critical fractile", value: fmtFractionPct(data.policy.critical_fractile) },
                  { key: "Cost ratio", value: `${data.policy.short_long_ratio.toFixed(2)} short / long` },
                  {
                    key: "Average hedge offset",
                    value: avgOffset === null ? "—" : `${fmtSigned(avgOffset)} MW`,
                  },
                  {
                    key: "Wind forecast range",
                    value: `${fmtInt(data.forecast.summary.wind_p10_mwh)} – ${fmtInt(
                      data.forecast.summary.wind_p90_mwh,
                    )} MWh`,
                  },
                  {
                    key: "Hours covered",
                    value: `${data.totals.hours_covered} / 24`,
                  },
                ]}
              />
              <div style={{ height: 12 }} />
              <Callout tone="accent" icon="◆">
                With a short:long cost ratio of {data.policy.short_long_ratio.toFixed(2)}, the optimal
                nomination sits at the {fmtFractionPct(data.policy.critical_fractile, 0)} percentile of wind
                — below the central forecast. That is why{" "}
                {fmtGwh(data.totals.risk_uplift_mwh)} GWh of extra thermal appears: it is insurance, priced
                by the residual distribution, not a view that wind will be low.
              </Callout>
            </Panel>
          </div>

          <Panel
            title="Hourly procurement plan"
            sub="MW by hour. Wind is nominated at the alpha-quantile; thermal covers the residual demand."
          >
            <div className="table-wrap" style={{ maxHeight: 440, overflowY: "auto" }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Hour</th>
                    <th>Demand</th>
                    <th>Wind (cal.)</th>
                    <th>P10</th>
                    <th>P90</th>
                    <th>Nominated</th>
                    <th>Thermal nominal</th>
                    <th>Thermal procured</th>
                    <th>Uplift</th>
                    <th>Shortfall</th>
                  </tr>
                </thead>
                <tbody>
                  {data.hours.map((row) => (
                    <tr key={row.hour}>
                      <td>{hourLabel(row.hour)}</td>
                      <td className="t-dim">{fmtInt(row.demand_mw)}</td>
                      <td className="t-accent">{fmtInt(row.wind_forecast_mw)}</td>
                      <td className="t-dim">{fmtInt(row.wind_p10_mw)}</td>
                      <td className="t-dim">{fmtInt(row.wind_p90_mw)}</td>
                      <td>{fmtInt(row.wind_nominated_mw)}</td>
                      <td className="t-dim">{fmtInt(row.thermal_baseline_mw)}</td>
                      <td>{fmtInt(row.thermal_procured_mw)}</td>
                      <td className="t-accent">{fmtSigned(row.uplift_mw)}</td>
                      <td className="t-dim">{fmtInt(row.exposure?.expected_shortfall_mw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ height: 10 }} />
            <p className="small muted">
              Thermal is computed as demand minus nominated wind. Negative thermal would mean the desk is a
              net exporter in that hour; the GB winter shape avoids it at these wind levels, but a low-demand
              or very high-wind scenario can produce it. {fmtGwh(data.totals.thermal_procured_mwh)} GWh of
              thermal energy over the day.
            </p>
          </Panel>
        </>
      )}
    </>
  );
}
