# Mandate Matcher — Technical Write-Up

## Scoring Logic

Each sell-side company receives an **engagement_fit_score** (range 1.0–3.0) computed as a weighted average of five qualitative dimensions:

| Dimension              | Weight | Notes                                      |
|------------------------|--------|--------------------------------------------|
| fee_model_openness     | 20%    | Direct: high=3, medium=2, low=1            |
| fixed_fee_resistance   | 20%    | Inverted: high resistance → low score      |
| mandate_clarity        | 20%    | Direct ordinal                             |
| process_discipline     | 20%    | Direct ordinal                             |
| seriousness            | 20%    | Direct ordinal                             |

Equal weighting reflects that all five dimensions are equally diagnostic of mandate quality at first-pass evaluation. The inversion of `fixed_fee_resistance` is intentional — high resistance to a structured fee model signals poor engagement readiness.

Classification thresholds:
- **Qualified**: score ≥ 2.0  
- **Watchlist**: score ≥ 1.3 (no hard disqualifier triggered)  
- **Disqualified**: score < 1.3, or a hard disqualifier fires

---

## Hard Disqualifiers

Two rules trigger automatic disqualification regardless of score:

**Rule 1 — Negative EBITDA + Low Seriousness**  
A loss-making company that also shows low engagement seriousness is not investable at this stage. Pursuing it would waste process bandwidth on both sides with no realistic path to close.

**Rule 2 — Low Mandate Clarity AND Low Process Discipline**  
Without a clear mandate and a structured process, no advisory engagement can succeed. These two are foundational prerequisites; either alone is manageable, but both failing together is disqualifying.

---

## Matching Logic

For each Qualified company, every buy-side entity is evaluated using a 10-point composite score:

| Component        | Max Points | Method                                          |
|------------------|------------|-------------------------------------------------|
| Geography match  | 2.0        | Binary — sell-side geo in buyer's focus list    |
| Sector match     | 2.0        | Binary — sell-side sector in buyer's focus list |
| Stage match      | 1.5        | Binary — sell-side stage in buyer's stage focus |
| Size fit         | 3.0        | Continuous — ticket & revenue range overlap     |
| Control fit      | 1.0        | Majority/minority mandate vs. buyer preference  |
| Relationship     | 0.5        | Bonus for existing relationship strength        |

Geography and sector are **hard filters** — a buyer with no overlap in either dimension receives no score and is excluded from consideration. Size fit uses a gradual decay function rather than a hard cutoff, rewarding partial overlaps proportionally.

The top 3 matches by score are returned per qualified company.

---

## What I Would Improve

1. **Score calibration with real data**: The current weights (20% each) are heuristic. With historical mandate outcomes, logistic regression or a simple ML model could learn which dimensions are truly predictive of successful engagement.

2. **Richer hard disqualifiers**: Real mandates often fail on relationship or reputational factors not captured in structured fields. A "red flag" tag or prior engagement history would strengthen the filter.

3. **Probabilistic matching**: Rather than a single match score, a confidence interval or Monte Carlo simulation over uncertain inputs (e.g., actual EBITDA vs. management projections) would better reflect real-world uncertainty.

4. **Interactive dashboard**: The current CLI output works for a prototype; production use would benefit from a web interface enabling filters, scenario testing, and export.
