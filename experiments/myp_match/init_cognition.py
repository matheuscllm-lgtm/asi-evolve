#!/usr/bin/env python3
"""Seed the cognition store for the myp_match experiment with domain knowledge.

Run once before evolving:  python experiments/myp_match/init_cognition.py

The knowledge below is distilled from myp-arbitrage-scanner/CLAUDE.md and the
classification rules in myp_arbitrage_scanner.py — it primes the Researcher so it
doesn't rediscover the rules.
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
            content="NM-only and EN-only are HARD invariants. A row whose condition is "
                    "not exactly Near-Mint ('NM') or whose language is not English ('EN') "
                    "must REJECT, no matter how large the margin. Match condition EXACTLY "
                    "(uppercase/strip first) — substring matching historically leaked 'SP' "
                    "into NM results. Never relax these to chase recall.",
            source="MYP CLAUDE.md / NM-only invariant (commit 42c86be)",
            metadata={"topic": "hard_invariants", "importance": "critical"},
        ),
        CognitionItem(
            content="Supranumerary rule: collector number > set denominator "
                    "(card_num > set_total, e.g. 226/217 or 097/086) means an IR/SIR/SAR "
                    "variant that MYP mislabels 'Comum'. Its margin is suspect (variant "
                    "misclassification). Guard against unparseable or zero denominators — "
                    "an unparseable (X/Y) should default to SAFE (do not over-flag).",
            source="myp_arbitrage_scanner.py H3 heuristic (v5.3/v5.8.5)",
            metadata={"topic": "supranumerary", "importance": "critical"},
        ),
        CognitionItem(
            content="TCG-suspect: declared TCG price >> last real sale signals a bad "
                    "card mapping (MYP .estat-tcg inflation -> fake margin). Production cuts "
                    "at ratio >= 10.0 (TCG_SUSPECT_RATIO_THRESHOLD). Real case: Jirachi PR-SM "
                    "declared R$1499 vs last sale R$19.99 = 75x -> suspect. The check only "
                    "runs when BOTH declared_tcg and a positive last_sale exist; a None "
                    "last_sale must not crash or falsely flag.",
            source="myp_arbitrage_scanner.py suspect check / Jirachi fixture",
            metadata={"topic": "tcg_suspect", "importance": "critical"},
        ),
        CognitionItem(
            content="Margin is GROSS and PURE: (tcg - myp)/myp, with NO embedded fees, "
                    "markup, FX, or shipping (cross-scanner policy 2026-06-06). The floor "
                    "MIN_MARGIN (production 0.30 = 30%) is a relevance gate, applied as "
                    "REJECT when margin < MIN_MARGIN. The R$50 price floor is a separate "
                    "upstream filter, not part of this contract. Threshold is a percent "
                    "integer in the scanner (30 = 30%); here it is the fraction 0.30.",
            source="MYP CLAUDE.md / feedback_gross_margin_only",
            metadata={"topic": "gross_margin", "importance": "high"},
        ),
        CognitionItem(
            content="pokemontcg.io (real TCGplayer price, USD->BRL live) is the GROUND "
                    "TRUTH since v5.11; the MYP `.estat-tcg` declared field is only a "
                    "fallback and mapped the WRONG card in Black Bolt/White Flare (Darumaka "
                    "097/086). When a real price overrides an inflated declared price, the "
                    "suspect flag is CLEARED. Trust the real reference; treat the declared "
                    "field as unreliable.",
            source="MYP CLAUDE.md / v5.11 + v5.11.3 A1",
            metadata={"topic": "ground_truth", "importance": "high"},
        ),
        CognitionItem(
            content="Precision over noise: marking a supranumerary or TCG-suspect row "
                    "CLEAN hands the operator a FAKE margin — far worse than dropping a real "
                    "deal. Optimize CLEAN-class F1 but never inflate clean by loosening the "
                    "suspect ratio or supranumerary rule. Check order matters: REJECT "
                    "invariants first, then supranumerary, then suspect; a row failing an "
                    "invariant must reject even if it would also be supranumerary/suspect.",
            source="operator rule (no purchase decisions) + check precedence",
            metadata={"topic": "precision_over_noise", "importance": "critical"},
        ),
    ]

    ids = cog.add_batch(knowledge)
    print(f"Seeded {len(ids)} cognition items into {exp_dir / 'cognition_data'}")


if __name__ == "__main__":
    init_cognition()
