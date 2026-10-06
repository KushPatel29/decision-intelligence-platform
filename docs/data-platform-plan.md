# Data platform plan: what analytics needs from IT, and how it is stored

A data scientist on a promotions, loyalty and pricing team does not own the source systems, but has to tell
the people who do exactly what is needed, at what grain, how fresh, and under what controls. This is that
request for the decisions this repository makes, written the way it would go to IT and data governance. The
layout it describes is the one the Databricks job builds (`databricks/`).

## 1. Decisions the data has to support

| Decision | Cadence | Latency it can tolerate |
|---|---|---|
| Monthly campaign plan (who gets which offer) | Monthly, re-solved on demand | Data to the end of the previous day |
| Offer and price test readouts | During and after each test | Daily |
| Capacity guardrail (free-flow headroom by zone and period) | Each plan, each test | Daily forecast, hourly profile |
| Model monitoring (drift, calibration) | Weekly | Weekly |

Nothing here needs streaming. A daily batch at 05:00 with a 23:59 cutoff covers every decision, and asking
IT for less than they might build is part of the request.

## 2. Fields requested, by source system

Each line is a field the pipeline actually consumes (`sql/customer_features.sql`, `features.py`,
`causal.py`, `optimization.py`). Anything not listed is not requested.

| Source | Grain | Fields | Why | Refresh |
|---|---|---|---|---|
| Trip / tolling system | One row per trip | trip id, customer id, entry and exit point, timestamp, distance, toll, discount, charged amount, vehicle class, ingestion batch id and time | Every behavioural feature, period mix, effective price per km, the capacity forecast | Daily, late-arriving trips flagged by batch |
| Account / CRM | One row per account, plus status history | customer and account id, type, created date, status, autopay, past due, transponder flag, home zone | Eligibility, tenure, segmentation | Daily; status as dated intervals, not overwrites |
| Consent and preferences | Dated history | marketing consent, My Account flag, effective from / to | Contact eligibility at the decision date; point-in-time correctness | Daily |
| Digital (app, web, email) | One row per event | event id, customer id, timestamp, event type, channel | Engagement and offer-funnel features | Daily |
| Loyalty | Ledger | points earned per trip, awards, redemptions, tier as of date | Points features, liability, the points cap in the plan | Daily |
| Campaign execution | Exposure, enrolment, redemption | customer, arm, offer, campaign id, timestamps, incentive cost | Test analysis, incentive cost, enrolment rates | Daily during campaigns |
| Pricing | Day × zone × period × segment | assigned price multiplier, effective price, demand | Elasticity identification | Daily during price tests |
| Operations / traffic | Zone × period | free-flow capacity, operating days | The capacity constraint | When capacity changes |
| External (public) | Day | weather, statutory holidays, CAD/USD | Demand context | Daily, cached with provenance hash |

## 3. Storage layout: medallion on Delta, governed in Unity Catalog

| Layer | Contents | Rules |
|---|---|---|
| Bronze | Each feed as delivered, with ingestion batch id and time | Append-only; never edited; kept so any silver row can be rebuilt |
| Silver | Conformed tables, one grain each, plus a quarantine table with a reason per rejected row | Natural-key de-duplication; contracts enforced as Delta CHECK constraints (`toll >= 0`, charge within toll, positive distance, known period); dated history for status and consent |
| Gold | Customer 360 and features, customer × offer, zone × day, campaign and loyalty performance, pricing elasticity | Point-in-time: features use only rows before the decision date; an informational primary key on every entity table |
| Serving | The decision snapshot (plan, candidates, policy comparison, capacity, prices) and a run receipt | Published only after the release gate and the reconciliation checks pass; hash manifest |

The defects the simulator plants in bronze (a late batch, a unit error on distances, a resent batch,
impossible charges) are the ones a real tolling feed produces, and the silver contract is written to catch
them: 4,147 of 3,684,396 bronze trips were quarantined in the committed run, each with its reason.

## 4. Point-in-time correctness

Every feature is computed "as of" a date from rows strictly before it, and every label window lies wholly
after it. Training, validation and test snapshots are separated so no 90-day label window crosses a fold
boundary. Status and consent are stored as dated intervals because a customer's eligibility in July has to
be read as it was in July, not as it is today. This is the single requirement most likely to be missed by a
warehouse built for reporting, and the reason the request asks for history rather than current state.

## 5. Access, privacy and retention

| Topic | Request |
|---|---|
| Identifiers | Analytics works on a stable surrogate customer id; names, addresses, plates and payment data are not requested |
| Access | Read on bronze/silver for the pipeline's service principal only; analysts read gold and serving; no one writes outside the job |
| Consent | Marketing consent is a filter in the plan's eligibility, not an afterthought; a withdrawn consent removes the customer from the next plan |
| Retention | Bronze 25 months (two full seasonal cycles plus a margin); silver and gold rebuilt from bronze; serving snapshots kept per release |
| Lineage | Each run records its source hashes, code version, model versions and a receipt row (`run_receipts`) |

## 6. Service levels asked of IT

| Item | Target |
|---|---|
| Daily feeds landed in bronze | 03:00 local, with a completeness signal per feed |
| Late or corrected batches | Flagged by batch id, never silently overwritten |
| Schema changes | Announced one release ahead; the schema registry (`docs/schema_registry.*`) versions the contract |
| Capacity reference data | Owned by operations, changed through a ticket, effective-dated |

## 7. Monitoring that comes with the data

The pipeline monitors the feeds as well as the models: daily volume against the same weekday's median
(flagging the planted late and duplicate batches), feature drift by population stability index, and the
calibration of the matured predictions. Flagged feed days and drifted features are reported for review
before a plan is used; the release gate itself is on model and plan quality. See the app's *Operations centre* page and `monitoring.py`.
