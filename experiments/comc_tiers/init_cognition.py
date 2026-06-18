#!/usr/bin/env python3
"""Seed the cognition store for the comc_tiers experiment with domain knowledge.

Run once before evolving:  python experiments/comc_tiers/init_cognition.py

The knowledge below is distilled from scanner-comc/CLAUDE.md and the matcher
source — it primes the Researcher so it doesn't rediscover the tier rules.
"""
import importlib.util
import sys
from pathlib import Path

# Register the asi-evolve repo root as the importable `Evolve` package, mirroring
# main.py's bootstrap, so this script works when run standalone.
REPO_ROOT = Path(__file__).resolve().parents[2]
if "Evolve" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "Evolve", REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)],
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["Evolve"] = _mod
    _spec.loader.exec_module(_mod)

from Evolve.cognition.cognition import Cognition          # noqa: E402
from Evolve.utils.structures import CognitionItem          # noqa: E402


def init_cognition():
    exp_dir = Path(__file__).parent
    cog = Cognition(storage_dir=exp_dir / "cognition_data")
    cog.reset()

    knowledge = [
        CognitionItem(
            content="The confidence tiers ladder by evidence strength: 0.95 = set + "
                    "collector number exact and UNIQUE (decisive); 0.90 = set + number "
                    "but >=2 variants, resolved by best-name disambiguation; 0.85 = number "
                    "present, no exact (set,number) hit, but strong fuzzy name within the "
                    "set; 0.70 = NO number, very strong & unambiguous name only. Anything "
                    "weaker REJECTs. A number is the strongest signal; name alone is the "
                    "weakest and needs the highest bar.",
            source="comc_scanner/matcher.py (tier semantics)",
            metadata={"topic": "tier_semantics", "importance": "critical"},
        ),
        CognitionItem(
            content="NAME_FLOOR = 45 is a SANITY floor, not a match threshold. Real COMC "
                    "'Pokemon' listings bleed in Topps/Bandai/etc. whose set strings can "
                    "resolve loosely; a mis-resolved set plus a coincidental collector "
                    "number must NOT pass at 0.95 with a wildly different name. The floor "
                    "guards exact-number tiers (0.95/0.90) against that false accept. Keep "
                    "it low enough that a genuine name-absent listing (number is decisive) "
                    "still passes.",
            source="comc_scanner/matcher.py (_NAME_FLOOR rationale)",
            metadata={"topic": "name_floor", "importance": "high"},
        ),
        CognitionItem(
            content="Precision over recall is the operator rule across all scanners: a WRONG "
                    "accept pairs a listing with the price of a DIFFERENT card and invents a "
                    "fake arbitrage margin (worse than a missed deal). Matches below 0.90 are "
                    "flagged 'validar' (review manually) downstream. When raising recall by "
                    "lowering a cutoff, watch the reject cases — a distractor that slips over "
                    "the bar is an expensive false positive.",
            source="scanner-comc/CLAUDE.md + cross-scanner operator rule",
            metadata={"topic": "precision_over_recall", "importance": "critical"},
        ),
        CognitionItem(
            content="Pipeline invariants from CLAUDE.md gate the listings BEFORE calibration: "
                    "piso de preco US$ 10 (carta valiosa >= ~R$50), NM-only and English-only "
                    "(other condition/language = false positive), and holofoil/subtype is "
                    "preferred via subtype_hint (Reverse Holofoil / 1st Edition / Unlimited / "
                    "Holofoil) so the reference price isn't overstated. This experiment tunes "
                    "the confidence tier that runs on the survivors, not these gates.",
            source="scanner-comc/CLAUDE.md (invariants)",
            metadata={"topic": "pipeline_invariants", "importance": "medium"},
        ),
        CognitionItem(
            content="The tunable levers are four thresholds: NAME_STRONG (90) = name bar when "
                    "a number is present but there's no exact (set,number) hit -> tier 0.85; "
                    "NAME_VERY_STRONG (92) = name bar when there's NO number at all -> tier "
                    "0.70; NAME_GAP (3) = how far the best name must beat the runner-up in the "
                    "no-number tier (guards against two equally-plausible candidates); and "
                    "NAME_FLOOR (45). Nudging 90/92 down lifts recall but risks accepting "
                    "distractors; widening NAME_GAP buys precision on ambiguous runner-ups.",
            source="comc_scanner/matcher.py (90 / 92 / gap-3 cutoffs)",
            metadata={"topic": "threshold_levers", "importance": "high"},
        ),
        CognitionItem(
            content="Calibration = for each predicted tier, the fraction of cases assigned to "
                    "it whose gold was a real match (1.0 = perfectly calibrated; lower = that "
                    "tier leaked rejects). A well-calibrated 0.95 bucket should be ~all true "
                    "matches; the 0.70 bucket is the riskiest because it rests on name only. "
                    "Optimize F1 AND keep high tiers clean — don't earn recall by dumping "
                    "shaky accepts into a high-confidence tier.",
            source="evaluator design (per-tier calibration metric)",
            metadata={"topic": "calibration", "importance": "high"},
        ),
    ]

    ids = cog.add_batch(knowledge)
    print(f"Seeded {len(ids)} cognition items into {exp_dir / 'cognition_data'}")


if __name__ == "__main__":
    init_cognition()
