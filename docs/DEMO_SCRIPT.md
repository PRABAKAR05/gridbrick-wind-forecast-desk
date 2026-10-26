# Demo video run sheet

Target: **9:30–9:50**, hard maximum 10:00. Unlisted YouTube. Part 1 is the customer pitch (≤5:00); Part 2 is the technical review (≤5:00). Record in one take if possible; the timer is the constraint, not perfection.

The recording is easier if the app is already warm. Start Docker and load the three main routes once before recording.

---

## Before recording

1. Start the app:
   ```bash
   docker compose up -d
   ```
2. Open <http://localhost:8088> and click through Decision Desk → Accuracy → Procurement → Method once. The first accuracy load takes 5–9 s.
3. Set browser zoom to 110–125% for legibility. Hide bookmarks and the taskbar where possible.
4. Use a 1920×1080 or 2560×1440 canvas. Close notifications.
5. Test the microphone for 10 seconds. Record the audio in the same take as the screen if you can; separate tracks make editing easier but add risk.
6. Have this run sheet on a second monitor or phone, not on screen.

Useful direct links:

- Desk, live: `http://localhost:8088/#/desk?d=2026-01-14&ch=9&cm=30`
- Desk, at gate: `http://localhost:8088/#/desk?d=2026-01-14&ch=9&cm=30&asof=2026-01-13T09:30:00.000Z`
- Accuracy: `http://localhost:8088/#/accuracy?d=2026-01-14`
- Procurement: `http://localhost:8088/#/procurement?d=2026-01-14`
- Method: `http://localhost:8088/#/method?d=2026-01-14`

---

# Part 1 — Customer pitch (0:00–5:00)

### 0:00–0:35 — The decision

**Say:**
> "It's 09:30 on 13 January 2026. A GB supplier has just passed day-ahead gate closure. It has to nominate how much wind it expects, and buy thermal cover for the rest of tomorrow. The latest Elexon wind forecast it can actually use was published at 07:30 — two hours earlier. GridBrick shows that forecast, and tells the desk how wrong forecasts like it have been."

**Do:** Open the Desk at gate link. Point at the clock chip and the staleness/publish time.

### 0:35–1:25 — The problem

**Say:**
> "Two traps. First, a dashboard that shows today's latest forecast and scores it against final outturn is leaking the future. Second, the raw WINDFOR feed is a forecast of total wind, while the outturn we can verify is transmission-metered wind. Comparing them directly leaves a +1.85 GW bias. A desk that trusts the raw number thinks there is 1.8 GW more wind than there is, buys too little thermal, and is short almost every day."

**Do:** Point at the raw versus calibrated headline numbers. Do not read every number.

### 1:25–2:35 — The decision desk

**Say:**
> "At the gate, the desk sees 230 GWh of raw wind. The recalibrated, decision-grade number is 213.6. The P10–P90 band is 178 to 292 GWh. The risk-adjusted nomination is 190 GWh — 23.5 GWh below the calibrated mean — because being short is 1.5 times as expensive as being long. That is the 40th percentile, not the average."

**Do:** Toggle from **At gate** to **Live**. Show that the forecast-side numbers stay identical; only the realised line and error appear. This is the product's core claim.

**Say:**
> "Nothing in the forecast changed when we moved the clock forward. That is point-in-time correctness, and it is enforced by a test."

### 2:35–3:35 — The evidence

**Say:**
> "Across all 744 hours in January, raw MAE is 2,142 MW. After walk-forward recalibration it is 1,370 MW, 36% better. Bias falls from 1,852 to 331 MW. The P10–P90 band covers 79.8% of outcomes against an 80% target. Every one of these numbers is computed from the vintage that was available at that day's gate — not from a hindsight forecast."

**Do:** Switch to Accuracy. Scroll slowly past the scorecards and the heatmap. Stop at reliability.

**Say:**
> "The tails are honest: the 90 and 95% bands under-cover, so the product treats P10–P90 as the operational band and says so."

### 3:35–4:35 — The purchase

**Say:**
> "This is where the error becomes money. Demand for the day is 1.145 TWh. Calibrated wind covers 213.6 GWh of it. The risk-adjusted plan nominates 190.1 GWh of wind and procures 954.8 GWh of thermal — 23.5 GWh more thermal than a mean-forecast plan. Expected shortfall is 14 GWh. Change the cost ratio and the whole plan moves; the assumption is explicit, not buried."

**Do:** Switch to Procurement. Drag or type a different short/long ratio and show the nomination and thermal uplift change.

### 4:35–5:00 — Close

**Say:**
> "GridBrick does not claim to make wind predictable. It makes the decision-time information honest, quantifies the residual error, and turns that error into a procurement quantity the desk can defend. The same method works for any delivery day in the pilot — and the entire thing runs offline from a committed Elexon snapshot."

**Do:** Return to the Desk at gate, full frame. Let the number sit for two seconds.

---

# Part 2 — Technical review (5:00–10:00)

### 5:00–5:40 — Architecture

**Say:**
> "Two services. A FastAPI backend over SQLite, seeded from committed gzipped JSONL, and a React/TypeScript SPA. In production they are one Vercel Services project: Vite at the root, FastAPI at /api, with the original path preserved. Locally they are two Docker containers behind nginx."

**Do:** Show the repository tree in an editor or terminal. Highlight `backend/app/domain`, `backend/app/services`, `frontend/src/pages`.

### 5:40–6:35 — The invariant

**Say:**
> "The central design decision is that every response is a function of data and as_of. A vintage is eligible only if publish_time is strictly before the cutoff. Actuals are filtered by their own publish_time at every use. Calibration and bands are walk-forward, fitted only on history that was available before the decision. This test asserts that the gate-time and live views of the same delivery day produce bit-identical forecast numbers."

**Do:** Open `backend/tests/test_api.py`, scroll to `test_point_in_time_forecast_is_invariant`. Then open `backend/app/services/analytics.py`, show the vintage selection and the comment about loading actuals in full.

**Say:**
> "That last comment is a real bug we fixed: filtering actuals at load time made the calibration depend on when a revision landed. Now visibility is enforced at the point of use, and the fit is reproducible."

### 6:35–7:35 — Calibration and bands

**Say:**
> "The recalibration is an affine OLS fit, outturn on forecast, over the trailing 14 days of decision-time vintages. The slope is bounded to 0.4 to 1.3 and we need 120 samples; otherwise we fall back to bias-only or identity. That guard rail matters: a bad window can make the forecast worse, but it cannot invert the signal. The current fit is slope 0.696, intercept +2,227 MW, 321 samples."

**Do:** Open `backend/app/domain/calibration.py`, show the bounds and fallback. Then Accuracy → Calibration chart.

**Say:**
> "Bands are empirical residual quantiles pooled by six-hour lead bucket. The residuals are homoscedastic — the correlation between absolute error and forecast level is 0.02 — but they cluster in time, so we inflate the band by 15% around the median instead of conditioning on level. The tails still under-cover, and the Method page says so."

### 7:35–8:25 — Procurement maths

**Say:**
> "The procurement rule is a newsvendor. With short cost 1.5 and long cost 1.0, the critical fractile is c_long over c_short plus c_long, 0.4. We nominate the 40th percentile. The offset is the negative of the 60th residual quantile. That sign was a real bug: the first version increased wind when shortfall was expensive. There is now a unit test for it."

**Do:** Open `backend/app/domain/procurement.py`, show `critical_fractile` and `hedge_offset`. Then `test_procurement.py`, show both sign tests.

### 8:25–9:10 — Operations and trade-offs

**Say:**
> "The warehouse is seeded deterministically, so the demo needs no API key and no network. On Vercel the SQLite file lives in /tmp and is rebuilt on cold start; that is a demo choice, not a production database. The accuracy report is the slow path at five to nine seconds; everything else is sub-second after warm-up. The frontend has no chart library: the SVG charts are hand-built so the axes and tooltips behave exactly as intended."

**Do:** Show the health endpoint or Docker logs if time. Otherwise stay on the Method page limitations.

### 9:10–10:00 — What I would do next

**Say:**
> "The honest limitations are sample size and scope. Thirty-one winter days is enough to demonstrate the method, not to size a real position. Next I would add multiple winters and weather regimes, store actual revisions rather than overwriting them, and replace the synthetic demand with the client's real demand forecast. The maths and the point-in-time contract are already in the right shape for that. The value here is not a better weather model — it is a decision surface that cannot cheat."

**Do:** End on the Method page limitations section. Stop recording at or before 10:00.

---

## If you overrun

Cut in this order:

1. The cost-ratio interaction in Part 1 (save 20 s).
2. The Docker/architecture detail in Part 2 (save 20 s).
3. The "what I would do next" list, keeping only sample size and revisions (save 15 s).

Never cut the gate-versus-live invariant demo in Part 1 or the invariant test in Part 2. Those are the product.

---

## YouTube upload

- Visibility: **Unlisted**.
- Title: `GridBrick — decision-time wind forecast intelligence (demo)`.
- Description: include the repo URL, the deployed URL, and a one-line note that the data is Elexon `FUELHH` + `WINDFOR` for January 2026.
- Thumbnail: Decision Desk at gate, readable at small size.
- Wait for HD processing before submitting.
- Watch the published video once in an **incognito** window. Check audio, captions if enabled, and that the video plays without sign-in.

## Final submission checklist

- [ ] Video is unlisted, ≤10:00, Part 1 ≤5:00 and Part 2 ≤5:00.
- [ ] GitHub repository is public and the name does not identify the candidate.
- [ ] README lists files/directories, how to start, deployed link, and AI usage.
- [ ] Deployed URL opens in an incognito window and is not password-protected.
- [ ] `/api/v1/health` returns `status: ok` from the deployed URL.
- [ ] The three main routes and one deep link work on the deployed URL.
- [ ] Submission form has the repo URL, video URL, and deployed URL.
- [ ] No secrets, `.env` files, local databases, or `.vercel` directories are committed.
