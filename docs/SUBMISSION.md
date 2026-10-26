# Submission pack

Copy the relevant answers into the assignment form. The repository and API are live now; claim the Vercel deployment to make the app URL permanent before submitting.

---

## One-line summary

GridBrick is a point-in-time wind forecast desk for GB day-ahead decisions: it shows the Elexon vintage actually available at gate closure, quantifies its error, and turns that error into a risk-adjusted wind nomination and thermal purchase.

## 100-word description

GridBrick answers two questions a UK supplier faces at 09:30 on D-1: what wind forecast could I actually have seen, and how wrong is it usually? It ingests Elexon `WINDFOR` vintages and `FUELHH` outturn, selects only forecasts published before the gate, and scores them against only the actuals visible at the same instant. A walk-forward affine recalibration removes a +1.85 GW scope bias, cutting MAE from 2,142 to 1,370 MW. Empirical P10–P90 bands are converted into a newsvendor wind nomination: for 14 January, 213.6 GWh of calibrated wind becomes a 190.1 GWh nomination and 23.5 GWh more thermal cover.

## 300-word description

Most wind-forecast dashboards are backtests with hindsight. They show the latest forecast, compare it with final outturn, and call that accuracy. A trading desk cannot use that: at gate closure it only has an older vintage, and it needs to know how large the residual error is before it sizes a position.

GridBrick is built around a point-in-time contract. Every API response is a function of `(data, as_of)`. A WINDFOR vintage is eligible only if its `publish_time` is strictly before the D-1 09:30 gate; FUELHH actuals are filtered by their own `publish_time`; and calibration and uncertainty bands are fitted walk-forward on trailing windows. A test asserts that the gate-time view and a later live view of the same delivery day return identical forecast-side numbers.

The pilot covers all 31 delivery days of January 2026. Raw WINDFOR has a 2,142 MW MAE and a +1,852 MW bias against transmission-metered outturn. The bias is structural: WINDFOR forecasts total wind, FUELHH measures transmission-metered wind. A bounded affine recalibration, fitted out-of-sample on 14-day trailing windows, reduces MAE to 1,370 MW and bias to 331 MW. P10–P90 coverage is 79.8% against an 80% target; the 90% and 95% tails are under-covered and are disclosed as such.

The procurement screen turns the residual distribution into a quantity. With shortfall 1.5× as expensive as surplus, the optimal wind nomination is the 40th percentile of the predictive distribution. For 14 January that is 190.1 GWh rather than the 213.6 GWh calibrated mean, and 954.8 GWh of thermal rather than 931.2 GWh. Demand is an explicit, clearly labelled synthetic input because the brief restricts the dataset to wind.

The stack is React/TypeScript/Vite, FastAPI/Python, SQLite, Docker and Vercel Services. The warehouse is seeded from a committed Elexon snapshot, so the demo is deterministic and works offline. The repository includes 25 tests, CI, a 10-minute demo script, and full deployment instructions.

## Links

- **Repository:** <https://github.com/PRABAKAR05/gridbrick-wind-forecast-desk>
- **Live app:** <https://flying-cygnus-lf7tsdl.tmp.now> — anonymous Vercel preview. Open the [claim link](https://vercel.com/claim-deployment?code=18b52160-c2e4-45a4-abda-058908527791) and sign in to make it permanent; the URL returns 403 until claimed.
- **Video:** [TO BE ADDED — unlisted YouTube URL]
- **API health:** <https://flying-cygnus-lf7tsdl.tmp.now/api/v1/health>
- **Demo script:** [`docs/DEMO_SCRIPT.md`](DEMO_SCRIPT.md)
- **Deployment notes:** [`docs/DEPLOY.md`](DEPLOY.md)

## What was built

| Area | Delivered |
|---|---|
| Product | Four-screen React app: Decision Desk, Accuracy, Procurement, Method |
| Backend | FastAPI, typed Pydantic contracts, point-in-time dataset, async BMRS client |
| Analytics | Calibration, reliability, skill benchmarks, error matrix, empirical bands |
| Decision maths | Newsvendor quantile, hedge offset, exposure, thermal plan |
| Data | 2,113 half-hour actuals, 25,696 forecast points, 352 vintages, committed seed |
| Quality | 25 pytest tests, ruff, ESLint, TypeScript typecheck, production build, CI |
| Packaging | Backend and frontend Dockerfiles, nginx, Compose, Vercel Services |
| Docs | README, deployment guide, demo run sheet, this pack |

## Key numbers to quote

- 31 delivery days, 744 hourly comparisons.
- Raw: MAE 2,142 MW, bias +1,852 MW, R² 0.803.
- Recalibrated: MAE 1,370 MW (−36%), bias +331 MW (−82%), R² 0.826.
- P10–P90 coverage: 79.8% (nominal 80%).
- Skill: 0.68 against persistence (4,272 MW MAE); beats 14-day climatology (3,738 MW MAE).
- 14 Jan: raw 230.1 GWh, calibrated 213.6 GWh, nominated 190.1 GWh, thermal 954.8 GWh, risk uplift 23.5 GWh, expected shortfall 14.0 GWh.

## Design decisions and trade-offs

- **Wind only.** The brief limits the dataset to Elexon wind. Demand is therefore an input, not a model, and the two profiles are labelled synthetic.
- **31 days is a demonstration, not a production sample.** The method is walk-forward and honest, but the sample cannot estimate seasonal or regime risk.
- **Affine, not causal.** The recalibration maps total wind to transmission-metered wind using recent behaviour. It is bounded and falls back gracefully, but it would fail if metering scope changed abruptly.
- **SQLite, not Postgres.** Zero-ops and deterministic for a demo; not a multi-user production store. On Vercel the file is rebuilt in `/tmp` on cold start.
- **No chart library.** Hand-built SVG keeps the axis behaviour and responsive layout predictable, at the cost of more code.
- **Strict cutoff.** `publish_time < cutoff` is used rather than `<=`, to avoid selecting a vintage stamped exactly at the gate. The result is a realistic 2.0-hour staleness at the default 09:30 gate.

## AI usage statement

AI was used substantially. The coding assistant was **OpenCode running DeepSeek V4.1 Flash Free**, supported by the `s0xdk/refactoring-ui` and `arla6ka/ui-review` UI review skills. AI assisted with architecture exploration, implementation, test generation, refactoring, UI copy and documentation. The author directed the product framing, data choices, point-in-time contract, model design and final numerical claims, and verified the analytics against raw BMRS responses. All numbers in this pack are reproducible from the committed seed and the running API. The only synthetic inputs are the two demand profiles, which are labelled as synthetic throughout.

## Before submitting

- [ ] Claim the Vercel deployment and replace the live link.
- [x] Create the public GitHub repository and replace the repository link.
- [ ] Record and upload the unlisted video; replace the video link.
- [ ] Open every link in an incognito window.
- [ ] Confirm the deployed app is not password-protected after claiming.
- [x] Confirm the repo contains no `.env`, database, `.vercel`, or credential files.
