# Mandate Matcher

A prototype system that qualifies sell-side M&A mandates and generates buy-side matches based on structured scoring logic.

## Structure

```
mandate-matcher/
├── data/
│   ├── sell_side.csv        # 14 sell-side mandate records
│   └── buy_side.csv         # 10 buy-side investor records
├── src/
│   └── mandate_matcher.py   # Main script (qualification + matching)
├── outputs/
│   ├── summary.csv          # Tabular results with top 3 matches
│   └── full_results.json    # Full structured output
├── WRITE_UP.md              # Scoring and logic explanation
└── README.md
```

## Requirements

Python 3.8+ — no external dependencies. Uses only the standard library (`csv`, `json`, `dataclasses`, `pathlib`).

## How to Run

```bash
python src/mandate_matcher.py
```

Output files are written to `outputs/`.

## What It Does

**Part 1 — Sell-Side Qualification**
- Computes an `engagement_fit_score` (1.0–3.0) from 5 weighted dimensions
- Applies 2 hard disqualifier rules before scoring
- Classifies each company as Qualified / Watchlist / Disqualified

**Part 2 — Buy-Side Matching**
- For each Qualified company, scores all buy-side entities on a 10-point scale
- Considers geography, sector, stage, deal size, control preference, and relationship strength
- Returns top 3 matches per company

**Part 3 — Outputs**
- Console report with emoji status indicators
- `summary.csv`: one row per company with scores and top 3 matches
- `full_results.json`: complete structured data for downstream use

## Key Design Decisions

- Equal weighting (20% each) across the 5 engagement dimensions — all are equally diagnostic at first pass
- `fixed_fee_resistance` is **inverted** in scoring (high resistance = low score)
- Geography + sector are **hard filters** in matching — a buyer must overlap on both to be considered
- Size fit uses a **continuous decay function** rather than a binary cutoff

See `WRITE_UP.md` for full explanation of logic, disqualifiers, and proposed improvements.
