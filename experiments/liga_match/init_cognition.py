#!/usr/bin/env python3
"""Seed the cognition store for the liga_match experiment with domain knowledge.

Run once before evolving:  python experiments/liga_match/init_cognition.py

The knowledge below is distilled from liga-cards-scanner/CLAUDE.md and the
matcher source — it primes the Researcher so it doesn't rediscover the rules.
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
            content="Liga lists cards by Brazilian set names / short codes; TCGplayer "
                    "uses canonical English set names. Short codes seen in the wild: "
                    "PRE=Prismatic Evolutions, SSP=Surging Sparks, JTG=Journey Together, "
                    "TWM=Twilight Masquerade, SCR=Stellar Crown, OBF=Obsidian Flames, "
                    "151=Scarlet & Violet 151 (TCG code MEW). Expand the alias map and/or "
                    "match when one set name is a token-subset of the other.",
            source="liga CLAUDE.md / set codes",
            metadata={"topic": "set_aliases", "importance": "critical"},
        ),
        CognitionItem(
            content="Normalize aggressively before scoring: lowercase, strip accents (NFKD), "
                    "collapse whitespace, drop punctuation (Mr. Mime == Mr Mime), and fold "
                    "V-MAX->VMAX, V-STAR->VSTAR, V-UNION->VUNION. The 'ex'/'EX' token is "
                    "SIGNIFICANT: 'Charizard ex' and 'Charizard' are different products.",
            source="normalization.py + card semantics",
            metadata={"topic": "normalization", "importance": "high"},
        ),
        CognitionItem(
            content="A WRONG match is worse than a missed one: pairing an offer with the "
                    "price of a different card invents a fake margin. Prefer precision. "
                    "When the best candidate's set similarity is weak, reject rather than "
                    "accept a same-name/different-set distractor.",
            source="operator rule (cross-scanner)",
            metadata={"topic": "precision_over_recall", "importance": "critical"},
        ),
        CognitionItem(
            content="Same card name can exist in multiple sets (Iono in Paldean Fates vs "
                    "Paldea Evolved) and same set can have regular vs Special Illustration "
                    "Rare variants. Name alone is ambiguous; the set component must carry "
                    "real disambiguating weight (current split: name 0.7 / set 0.3).",
            source="card_matcher.py",
            metadata={"topic": "disambiguation", "importance": "high"},
        ),
        CognitionItem(
            content="Token-aware similarity (e.g. token-set / Jaccard over words, or a "
                    "containment bonus) usually beats raw difflib character ratio for set "
                    "names where one side is a short code or a subset of the other "
                    "('151' subset of 'scarlet & violet 151').",
            source="matching heuristic",
            metadata={"topic": "similarity_function", "importance": "high"},
        ),
        CognitionItem(
            content="The acceptance threshold trades precision for recall. Lowering it blindly "
                    "lets distractors through (the reject cases guard against this). Tune the "
                    "scorer first; adjust FUZZY_THRESHOLD only as a final, validated step.",
            source="evaluator design",
            metadata={"topic": "threshold", "importance": "medium"},
        ),
    ]

    ids = cog.add_batch(knowledge)
    print(f"Seeded {len(ids)} cognition items into {exp_dir / 'cognition_data'}")


if __name__ == "__main__":
    init_cognition()
