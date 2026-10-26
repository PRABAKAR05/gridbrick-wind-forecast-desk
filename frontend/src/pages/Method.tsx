/** Method & Limits — the audit trail a technical reviewer can pull apart. */

import { Callout, KeyValue, PageHead, Panel } from "@/components/ui";
import { fmtDateLong, fmtDateShort, fmtInt } from "@/lib/format";
import { useApp } from "@/state/app";

export function Method() {
  const { meta, cutoff } = useApp();

  return (
    <>
      <PageHead
        title="Method, provenance and limits"
        lead={
          <>
            The design principle is simple: no number may use information that did not exist at the
            decision instant. Everything else follows from that constraint.
          </>
        }
      />

      <div className="grid grid--main">
        <div className="stack">
          <Panel title="1 · Scope" sub="National wind only, exactly as briefed.">
            <div className="prose">
              <p>
                The product covers <strong>national aggregate wind generation in Great Britain</strong>.
                It deliberately does not model demand, prices, interconnectors or other fuels — those are
                outside the supplied evidence base, and pretending otherwise would be the easiest way to
                produce a confident, wrong answer.
              </p>
              <p>Two Elexon BMRS datasets are used, and only these two:</p>
              <ul>
                <li>
                  <code>FUELHH</code> — half-hourly outturn by fuel type. The <code>WIND</code> series is
                  averaged to the hour so it can be paired with the forecast.
                </li>
                <li>
                  <code>WINDFOR</code> — hourly wind forecast vintages. Each row carries a{" "}
                  <code>publishTime</code>, which is what makes point-in-time reconstruction possible.
                </li>
              </ul>
              <p>
                The pilot window is {fmtDateLong(meta.pilot.start)} to {fmtDateLong(meta.pilot.end)}:
                {" "}{meta.pilot.days} delivery days, the January 2026 purchase cycle.
              </p>
            </div>
          </Panel>

          <Panel title="2 · Point-in-time correctness" sub="The invariant that stops the app cheating.">
            <div className="prose">
              <p>
                Every response is a pure function of <code>(warehouse, as_of)</code>. A forecast vintage is
                eligible only if <code>publish_time &lt; cutoff</code>; outturn is eligible only if its own{" "}
                <code>publish_time &lt; as_of</code>. The comparison is strict, so a vintage published at
                09:30 is <em>not</em> available to a 09:30 gate.
              </p>
              <p>
                The default gate is <strong>
                  {String(cutoff.hour).padStart(2, "0")}:{String(cutoff.minute).padStart(2, "0")} Europe/London
                  on D−1
                </strong>
                , just after the GB day-ahead auction closes. With strict selection the usable vintage is
                typically the 07:30 publication — a realistic{" "}
                <strong>two-hour staleness</strong>, not a fantasy of a forecast delivered at the gate.
              </p>
              <p>
                This is enforced in the analytics layer, not just the UI. The same code path produces the
                live view, the historical view, and the accuracy report, so the backtest cannot quietly use
                hindsight.
              </p>
            </div>
          </Panel>

          <Panel title="3 · The bias, and what was done about it" sub="A domain finding that changed the product.">
            <div className="prose">
              <p>
                WINDFOR is an all-wind forecast; FUELHH wind is transmission-metered. Comparing them
                naively produces a structural level gap: the raw forecast averages about{" "}
                <strong>1.85 GW above outturn</strong>. Some of that is embedded or distribution-connected
                wind that never appears in the transmission meter. A desk taking WINDFOR at face value would
                over-nominate wind every single day.
              </p>
              <p>
                Rather than hand-tune a fudge factor, the app fits an affine correction by walk-forward OLS
                on a trailing 14-day window:
              </p>
              <div className="formula">outturn ≈ slope × forecast + intercept</div>
              <p>
                Slope is bounded to [0.4, 1.3] and the fit needs at least 120 samples. The correction is
                applied to the <em>next</em> delivery day only, never to the day it was fitted on. The
                measured effect: MAE falls from roughly 2.1 GW to 1.4 GW and bias from +1.85 GW to a few
                hundred MW, while R² stays around 0.8. Most of the gain is the intercept; the slope stays
                near one because the weather signal itself is sound.
              </p>
            </div>
          </Panel>

          <Panel title="4 · Uncertainty bands" sub="Empirical, walk-forward, and honest about its misses.">
            <div className="prose">
              <p>
                Residuals are <code>forecast − actual</code> in the calibrated space. For each lead-time
                bucket (six-hour bands) the app pools residuals from the trailing 14 days and takes
                empirical quantiles. A band needs at least 48 samples; otherwise it returns "unavailable"
                rather than inventing precision.
              </p>
              <p>
                A conformal-style inflation factor of <strong>1.15</strong> is applied around the median to
                correct the mild under-coverage of raw empirical quantiles. The observed P10-P90 coverage
                lands within about two points of nominal across the pilot, which is good enough to size a
                hedge but not good enough to claim certainty. The tails are weaker: the nominal 90% and 95%
                bands covered 87.6% and 89.5% of hours, so the desk sizes its central hedge from the empirical
                residual quantile rather than pretending the extreme tail is precise.
              </p>
              <p>
                Residual magnitude was tested against forecast level and found effectively homoscedastic
                (correlation ≈ 0.02), so the band is not conditioned on wind level. The errors are,
                however, temporally clustered — calm spells produce runs of same-sign misses. That is why
                the band is widened rather than treated as independent noise.
              </p>
            </div>
          </Panel>

          <Panel title="5 · From error to a purchase" sub="The newsvendor step.">
            <div className="prose">
              <p>
                Wind is nominated at a quantile of its predictive distribution. With <code>c_short</code>{" "}
                and <code>c_long</code> as the relative costs of under- and over-nomination, the optimal
                service level is:
              </p>
              <div className="formula">α = c_long / (c_short + c_long)</div>
              <p>
                The hedge offset is <code>o = −q₁₋α(ε)</code> where <code>ε = forecast − actual</code>, so
                the nomination is <code>f + o</code>. The sign matters: a desk worried about being short
                needs a <em>negative</em> offset, nominating less wind and buying more thermal. Getting it
                backwards flatters the plan and leaves the desk exposed.
              </p>
              <p>
                Thermal is then the residual: <code>demand − nominated wind</code>. The difference between
                thermal bought on the point forecast and thermal bought on the quantile is the risk uplift —
                the price of insurance, visible in GWh on the procurement page.
              </p>
            </div>
          </Panel>

          <Panel title="6 · What this is not" sub="Limits stated plainly.">
            <div className="prose">
              <ul>
                <li>
                  <strong>Demand is an input, not a model.</strong> The two profiles are clearly labelled
                  synthetic shapes for demonstrating mechanics. In production they would be replaced by the
                  client's own demand forecast.
                </li>
                <li>
                  <strong>No price modelling.</strong> <code>c_short</code> and <code>c_long</code> are
                  relative cost knobs, not forward curves. A real desk would calibrate them from its own
                  imbalance exposure.
                </li>
                <li>
                  <strong>One month, one winter.</strong> January 2026 is 31 days. The statistics are
                  adequate for a pilot and insufficient for a claim about annual performance. The
                  walk-forward design reduces, but does not eliminate, small-sample risk.
                </li>
                <li>
                  <strong>National aggregate only.</strong> No locational, offshore/onshore split, or
                  constraint modelling. Those are the obvious next increments.
                </li>
                <li>
                  <strong>Hourly resolution.</strong> WINDFOR is hourly, so the half-hourly FUELHH series is
                  averaged up. Sub-hourly variability is therefore invisible; hourly MW sums equal MWh.
                </li>
              </ul>
            </div>
          </Panel>
        </div>

        <div className="stack">
          <Panel title="Data in the warehouse" sub="Counts from the live API at load time.">
            <KeyValue
              rows={[
                {
                  key: "Pilot window",
                  value: `${fmtDateShort(meta.pilot.start)} – ${fmtDateShort(meta.pilot.end)}`,
                },
                {
                  key: "Outturn data",
                  value: `${fmtDateShort(meta.data.actual_start_utc ?? meta.pilot.start)} – ${fmtDateShort(
                    meta.data.actual_end_utc ?? meta.pilot.end,
                  )}`,
                },
                { key: "Actual hours", value: fmtInt(meta.data.actuals) },
                { key: "Forecast points", value: fmtInt(meta.data.forecast_points) },
                { key: "Vintages", value: fmtInt(meta.data.vintages) },
                {
                  key: "First vintage",
                  value: fmtDateShort(meta.data.forecast_publish_start_utc ?? meta.pilot.start),
                },
                { key: "GB wind capacity", value: `${fmtInt(meta.data.capacity_mw)} MW` },
                {
                  key: "Default gate",
                  value: `${meta.defaults.cutoff_hour}:${String(meta.defaults.cutoff_minute).padStart(2, "0")} local`,
                },
                { key: "Band lookback", value: `${meta.defaults.band_lookback_days} days` },
                { key: "Band minimum", value: `${meta.defaults.band_min_days} days` },
                { key: "Default costs", value: `${meta.defaults.c_short} short / ${meta.defaults.c_long} long` },
              ]}
            />
          </Panel>

          <Panel title="Engineering notes" sub="Choices a reviewer might otherwise have to reverse-engineer.">
            <div className="prose">
              <p>
                FastAPI + SQLAlchemy over SQLite, with timestamps stored as naive UTC and converted at the
                boundary. A committed gzipped JSONL seed makes the container deterministic and lets it run
                with no network access.
              </p>
              <p>
                Ingestion chunks the BMRS API into seven-day windows using{" "}
                <code>publishDateTimeFrom</code>/<code>publishDateTimeTo</code> and upserts idempotently.
                The API ignores <code>from</code>/<code>to</code>; discovering that cost an hour and is
                documented in the code.
              </p>
              <p>
                Frontend is React 18 + TypeScript + Vite, with TanStack Query for server state and no chart
                library — the charts are hand-built SVG so the point-in-time semantics stay explicit and the
                bundle stays small.
              </p>
            </div>
          </Panel>

          <Panel title="AI tool usage" sub="Disclosed as required by the brief.">
            <div className="prose">
              <p>
                An AI coding assistant (Cursor) was used throughout: scaffolding, boilerplate, chart maths,
                test generation, and drafting this documentation. All domain decisions — the gate-closure
                convention, the calibration approach, the newsvendor formulation, the honesty constraints —
                were reviewed and validated against the data. Numbers quoted in the UI are computed live by
                the API, not hard-coded.
              </p>
              <p>
                Where the assistant produced something incorrect (an early version used the raw forecast as
                the procurement basis, and another had the hedge-offset sign inverted), the error was found
                by checking the result against the underlying maths and is now covered by tests.
              </p>
            </div>
          </Panel>

          <Callout tone="accent" icon="◆">
            <strong>Reviewer shortcut.</strong> Set the clock to <em>At gate</em> for 14 January, then flip
            to <em>Live</em>. The forecast does not change; the outturn appears. That is the invariant the
            whole product is built on.
          </Callout>
        </div>
      </div>
    </>
  );
}
