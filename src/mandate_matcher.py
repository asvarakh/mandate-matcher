"""
mandate_matcher.py
------------------
Sell-side mandate qualification + buy-side matching engine.
Author: Avyay
"""

import csv
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path

# ─────────────────────────────────────────────
# 0. CONFIGURATION
# ─────────────────────────────────────────────

DATA_DIR   = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Score weights for engagement_fit_score (must sum to 1.0)
WEIGHTS = {
    "fee_model_openness":   0.20,
    "fixed_fee_resistance": 0.20,   # inverted: high resistance = low score
    "mandate_clarity":      0.20,
    "process_discipline":   0.20,
    "seriousness":          0.20,
}

# Ordinal map: qualitative labels → numeric score
ORDINAL = {"high": 3, "medium": 2, "low": 1}

# Classification thresholds (out of max score 3.0)
THRESHOLDS = {
    "qualified":  2.0,   # engagement_fit_score >= 2.0
    "watchlist":  1.3,   # engagement_fit_score >= 1.3
    # below 1.3 → Disqualified
}


# ─────────────────────────────────────────────
# 1. DATA LOADING HELPERS
# ─────────────────────────────────────────────

def load_csv(path: Path) -> List[Dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(value: str) -> int:
    return int(value.replace(",", "").strip())


# ─────────────────────────────────────────────
# 2. SELL-SIDE QUALIFICATION
# ─────────────────────────────────────────────

@dataclass
class QualificationResult:
    company_name: str
    geography: str
    sector: str
    stage: str
    mandate_type: str
    revenue: int
    EBITDA: int
    capital_sought: int
    fee_model_openness: str
    fixed_fee_resistance: str
    mandate_clarity: str
    process_discipline: str
    seriousness: str
    engagement_fit_score: float = 0.0
    status: str = ""
    disqualify_reason: Optional[str] = None
    top_matches: List[Dict] = field(default_factory=list)


def score_company(company: Dict) -> float:
    """
    Weighted average of five ordinal dimensions.
    'fixed_fee_resistance' is inverted (high resistance = penalty).
    Returns a score in [1.0, 3.0].
    """
    raw = {}
    for dim in WEIGHTS:
        val = ORDINAL.get(company[dim].strip().lower(), 1)
        if dim == "fixed_fee_resistance":
            val = 4 - val          # invert: high=1, medium=2, low=3
        raw[dim] = val

    score = sum(raw[dim] * WEIGHTS[dim] for dim in WEIGHTS)
    return round(score, 3)


def hard_disqualify(company: Dict) -> Optional[str]:
    """
    Hard disqualifiers — automatic rejection regardless of score.

    Rule 1: EBITDA negative AND seriousness is 'low'
        Rationale: Loss-making companies with low seriousness are not
        investable at this stage; pursuing them wastes process bandwidth.

    Rule 2: Both mandate_clarity AND process_discipline are 'low'
        Rationale: Without clear mandate and structured process, no
        advisory engagement can succeed. This is a foundational minimum.
    """
    ebitda    = to_int(company["EBITDA"])
    serious   = company["seriousness"].strip().lower()
    clarity   = company["mandate_clarity"].strip().lower()
    discipline= company["process_discipline"].strip().lower()

    if ebitda < 0 and serious == "low":
        return "DISQUALIFIED: Negative EBITDA + low seriousness"

    if clarity == "low" and discipline == "low":
        return "DISQUALIFIED: Low mandate clarity AND low process discipline"

    return None


def classify(score: float) -> str:
    if score >= THRESHOLDS["qualified"]:
        return "Qualified"
    elif score >= THRESHOLDS["watchlist"]:
        return "Watchlist"
    else:
        return "Disqualified"


def qualify_sell_side(sell_side: List[Dict]) -> List[QualificationResult]:
    results = []
    for c in sell_side:
        result = QualificationResult(
            company_name        = c["company_name"],
            geography           = c["geography"],
            sector              = c["sector"],
            stage               = c["stage"],
            mandate_type        = c["mandate_type"],
            revenue             = to_int(c["revenue"]),
            EBITDA              = to_int(c["EBITDA"]),
            capital_sought      = to_int(c["capital_sought"]),
            fee_model_openness  = c["fee_model_openness"],
            fixed_fee_resistance= c["fixed_fee_resistance"],
            mandate_clarity     = c["mandate_clarity"],
            process_discipline  = c["process_discipline"],
            seriousness         = c["seriousness"],
        )

        # Check hard disqualifiers first
        disq = hard_disqualify(c)
        if disq:
            result.engagement_fit_score = score_company(c)
            result.status = "Disqualified"
            result.disqualify_reason = disq
        else:
            score = score_company(c)
            result.engagement_fit_score = score
            status = classify(score)
            result.status = status

        results.append(result)

    return results


# ─────────────────────────────────────────────
# 3. BUY-SIDE MATCHING
# ─────────────────────────────────────────────

def geography_overlap(sell_geo: str, buy_geo: str) -> bool:
    """True if sell-side geography appears in buyer's focus list."""
    buy_geos = [g.strip().lower() for g in buy_geo.split(";")]
    return sell_geo.strip().lower() in buy_geos


def sector_overlap(sell_sector: str, buy_sector: str) -> bool:
    """True if sell-side sector appears in buyer's sector focus list."""
    buy_sectors = [s.strip().lower() for s in buy_sector.split(";")]
    return sell_sector.strip().lower() in buy_sectors


def stage_overlap(sell_stage: str, buy_stage: str) -> bool:
    """True if sell-side stage matches any buyer stage focus."""
    buy_stages = [s.strip().lower() for s in buy_stage.split(";")]
    return sell_stage.strip().lower() in buy_stages


def size_score(capital_sought: int, ticket_min: int, ticket_max: int,
               revenue: int, rev_min: int, rev_max: int) -> float:
    """
    Returns 0.0–1.0 measuring how well the deal size fits the buyer.
    Checks both ticket size and revenue range; averages the two.
    """
    # Ticket fit
    if ticket_min <= capital_sought <= ticket_max:
        ticket_fit = 1.0
    elif capital_sought < ticket_min:
        ticket_fit = max(0.0, 1 - (ticket_min - capital_sought) / ticket_min)
    else:
        ticket_fit = max(0.0, 1 - (capital_sought - ticket_max) / ticket_max)

    # Revenue fit
    if rev_min <= revenue <= rev_max:
        rev_fit = 1.0
    elif revenue < rev_min:
        rev_fit = max(0.0, 1 - (rev_min - revenue) / rev_min)
    else:
        rev_fit = max(0.0, 1 - (revenue - rev_max) / rev_max)

    return round((ticket_fit + rev_fit) / 2, 3)


def control_fit(mandate_type: str, control_pref: str) -> float:
    """
    Returns 1.0 if control preference aligns with mandate type, else 0.5.
    Full Sale / Majority Equity → buyer should prefer majority.
    Minority Equity → buyer should prefer minority.
    """
    majority_mandates = {"full sale", "majority equity"}
    sell_is_majority = mandate_type.strip().lower() in majority_mandates
    buy_wants_majority = control_pref.strip().lower() == "majority"

    if sell_is_majority == buy_wants_majority:
        return 1.0
    return 0.5


def relationship_bonus(rel_strength: str) -> float:
    """Small uplift for existing relationship strength."""
    mapping = {"strong": 0.1, "medium": 0.05, "weak": 0.0}
    return mapping.get(rel_strength.strip().lower(), 0.0)


def match_score(sell: QualificationResult, buyer: Dict) -> Optional[float]:
    """
    Computes a match score [0, 10] for a qualified sell-side company
    against a buy-side entity.

    Component weights:
      Geography match  : 2.0 pts (binary)
      Sector match     : 2.0 pts (binary)
      Stage match      : 1.5 pts (binary)
      Size fit         : 3.0 pts (continuous 0–1 scaled)
      Control fit      : 1.0 pt  (binary-ish)
      Relationship      : 0.5 pt  (bonus)

    Returns None if geography or sector don't match (hard filter).
    """
    geo_match    = geography_overlap(sell.geography, buyer["geography_focus"])
    sector_match = sector_overlap(sell.sector,    buyer["sector_focus"])

    # Hard filters: geography + sector must overlap
    if not geo_match or not sector_match:
        return None

    stage_match  = stage_overlap(sell.stage, buyer["stage_focus"])
    sz           = size_score(
                       sell.capital_sought,
                       to_int(buyer["ticket_size_min"]),
                       to_int(buyer["ticket_size_max"]),
                       sell.revenue,
                       to_int(buyer["revenue_range_min"]),
                       to_int(buyer["revenue_range_max"]),
                   )
    ctrl         = control_fit(sell.mandate_type, buyer["control_preference"])
    rel          = relationship_bonus(buyer["relationship_strength"])

    score = (
        2.0 * geo_match    +
        2.0 * sector_match +
        1.5 * stage_match  +
        3.0 * sz           +
        1.0 * ctrl         +
        rel
    )
    return round(min(score, 10.0), 2)


def match_buy_side(qualified: List[QualificationResult],
                   buy_side: List[Dict]) -> None:
    """Mutates each qualified result: adds top_matches list."""
    for sell in qualified:
        if sell.status != "Qualified":
            continue

        scores = []
        for buyer in buy_side:
            s = match_score(sell, buyer)
            if s is not None:
                scores.append({
                    "investor_name": buyer["investor_name"],
                    "player_type":   buyer["player_type"],
                    "match_score":   s,
                })

        # Sort descending, take top 3
        scores.sort(key=lambda x: x["match_score"], reverse=True)
        sell.top_matches = scores[:3]


# ─────────────────────────────────────────────
# 4. OUTPUT
# ─────────────────────────────────────────────

def write_outputs(results: List[QualificationResult]) -> None:
    # ── 4a. Full detail JSON ──────────────────────────────────────────
    json_path = OUTPUT_DIR / "full_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"[✓] JSON written → {json_path}")

    # ── 4b. Summary CSV ───────────────────────────────────────────────
    csv_path = OUTPUT_DIR / "summary.csv"
    fieldnames = [
        "company_name", "sector", "geography", "stage", "mandate_type",
        "revenue", "EBITDA", "capital_sought",
        "engagement_fit_score", "status", "disqualify_reason",
        "match_1_investor", "match_1_score",
        "match_2_investor", "match_2_score",
        "match_3_investor", "match_3_score",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            m = r.top_matches
            row = {
                "company_name":        r.company_name,
                "sector":              r.sector,
                "geography":           r.geography,
                "stage":               r.stage,
                "mandate_type":        r.mandate_type,
                "revenue":             r.revenue,
                "EBITDA":              r.EBITDA,
                "capital_sought":      r.capital_sought,
                "engagement_fit_score":r.engagement_fit_score,
                "status":              r.status,
                "disqualify_reason":   r.disqualify_reason or "",
                "match_1_investor":    m[0]["investor_name"] if len(m) > 0 else "",
                "match_1_score":       m[0]["match_score"]   if len(m) > 0 else "",
                "match_2_investor":    m[1]["investor_name"] if len(m) > 1 else "",
                "match_2_score":       m[1]["match_score"]   if len(m) > 1 else "",
                "match_3_investor":    m[2]["investor_name"] if len(m) > 2 else "",
                "match_3_score":       m[2]["match_score"]   if len(m) > 2 else "",
            }
            writer.writerow(row)
    print(f"[✓] CSV written  → {csv_path}")


# ─────────────────────────────────────────────
# 5. PRETTY CONSOLE REPORT
# ─────────────────────────────────────────────

def print_report(results: List[QualificationResult]) -> None:
    STATUS_ICON = {"Qualified": "✅", "Watchlist": "⚠️ ", "Disqualified": "❌"}
    print("\n" + "═" * 70)
    print("  MANDATE MATCHER — RESULTS REPORT")
    print("═" * 70)

    for r in results:
        icon = STATUS_ICON.get(r.status, "?")
        print(f"\n{icon}  {r.company_name:<30} [{r.status}]  score={r.engagement_fit_score}")
        if r.disqualify_reason:
            print(f"      ↳ {r.disqualify_reason}")
        if r.top_matches:
            for i, m in enumerate(r.top_matches, 1):
                print(f"      Match {i}: {m['investor_name']:<28} score={m['match_score']}/10")

    # Summary stats
    statuses = [r.status for r in results]
    print("\n" + "─" * 70)
    print(f"  Total: {len(results)} | "
          f"Qualified: {statuses.count('Qualified')} | "
          f"Watchlist: {statuses.count('Watchlist')} | "
          f"Disqualified: {statuses.count('Disqualified')}")
    print("═" * 70 + "\n")


# ─────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────

def main():
    print("Loading data...")
    sell_side = load_csv(DATA_DIR / "sell_side.csv")
    buy_side  = load_csv(DATA_DIR / "buy_side.csv")
    print(f"  Sell-side records: {len(sell_side)}")
    print(f"  Buy-side records:  {len(buy_side)}")

    print("\nRunning sell-side qualification...")
    results = qualify_sell_side(sell_side)

    print("Running buy-side matching for qualified companies...")
    match_buy_side(results, buy_side)

    print_report(results)
    write_outputs(results)


if __name__ == "__main__":
    main()
